package repro;
import java.util.*;
import java.io.*;
import java.nio.file.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.core.*;
import org.cloudbus.cloudsim.power.PowerDatacenter;

/** Supply-aware PowerDatacenter: actual Host feedback, UPS and timed VM migration. */
public final class ResearchDatacenter extends PowerDatacenter implements AutoCloseable {
    public static final double ORIGIN=1;private static final int TICK=9201,FINISH=CloudSimTags.VM_MIGRATE;
    public final PaperSettings s;public final ResearchRun.Workload w;public final SupplyPowerModel model;
    public double serverJ,upsJ,hostModelJ,hardwareJ,requestedMI,deliveredMI,migrationSeconds,cpuCheckError;
    public final ResearchConfig cfg;private double hardware;private final double[] auxiliaryPower;
    public int starts,finishes,blocked,samples;public boolean ended;
    public RuntimeException failure;
    public final long[] baselineMI;
    private double last=ORIGIN,server,loss,requested,delivered;private final double[] rackPower;
    private final Map<Integer,Map<String,Object>> pending=new HashMap<>();
    private final List<Map<String,Object>> deferredUnderload=new ArrayList<>();
    private final PrintWriter times,segments,events,hosts,assignments;
    public ResearchDatacenter(ResearchRun.Workload w,ResearchConfig cfg,Path prefix,boolean detailed) throws Exception {
        this(w,cfg,cfg.settings,prefix,detailed);
    }
    private ResearchDatacenter(ResearchRun.Workload w,ResearchConfig cfg,PaperSettings s,Path prefix,boolean detailed) throws Exception {
        super("ResearchDatacenter",new DatacenterCharacteristics("x86","Linux","Xen",w.hosts,8,0,0,0,0),
                w.policy,new LinkedList<Storage>(),s.step);this.cfg=cfg;auxiliaryPower=new double[s.hosts];this.s=s;this.w=w;model=new SupplyPowerModel(s);rackPower=new double[s.racks];baselineMI=new long[w.trace.length];
        if(prefix!=null)Files.createDirectories(prefix.getParent());
        times=writer(prefix,"_times.csv");segments=writer(prefix,"_segments.csv");events=writer(prefix,"_events.csv");
        hosts=detailed?writer(prefix,"_hosts.csv"):null;assignments=detailed?writer(prefix,"_assignments.csv"):null;
        if(times!=null)times.println("time_s,server_w,ups_loss_w,total_w,active_hosts,started,finished,pending,requested_mips,delivered_mips");
        if(segments!=null){segments.print("begin_s,end_s,server_w,ups_loss_w,requested_mips,delivered_mips,pending");
            for(int r=0;r<s.racks;r++)segments.print(",rack"+r+"_output_w,rack"+r+"_loss_w");segments.println(",host_model_w,hardware_w");}
        if(events!=null)events.println("time_s,event,vm_id,source_host,target_host,source_cpu,ram_mb,bandwidth_kbps,reason");
        if(hosts!=null)hosts.println("time_s,host_id,cpu,service_mips,requested_mips,power_w,vm_entries,incremental_w");
        if(assignments!=null)assignments.println("time_s,vm_id,host_id,raw_cpu,requested_mips,allocated_mips,in_migration");
    }
    private static PrintWriter writer(Path p,String suffix) throws Exception{return p==null?null:new PrintWriter(p+suffix,"UTF-8");}
    @Override public void processEvent(SimEvent event){try{super.processEvent(event);}catch(RuntimeException error){failure=error;CloudSim.stopSimulation();}}
    @Override public void startEntity(){super.startEntity();schedule(getId(),ORIGIN,TICK,Integer.valueOf(0));}
    @Override protected void updateCloudletProcessing(){/* Boundary events prevent duplicate PowerDatacenter ticks. */}
    private void advance(){double time=CloudSim.clock(),dt=time-last;if(time<ORIGIN)return;
        if(dt>1e-9){serverJ+=server*dt;hostModelJ+=(server-hardware)*dt;hardwareJ+=hardware*dt;upsJ+=loss*dt;requestedMI+=requested*dt;deliveredMI+=delivered*dt;migrationSeconds+=pending.size()*dt;
            if(segments!=null){segments.printf(Locale.US,"%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%d",last-ORIGIN,time-ORIGIN,server,loss,requested,delivered,pending.size());
                for(double r:rackPower)segments.printf(Locale.US,",%.9f,%.9f",r,model.loss(r));segments.printf(Locale.US,",%.9f,%.9f%n",server-hardware,hardware);}}
        for(PaperHost h:w.hosts)h.updateVmsProcessing(time);last=time;
    }
    private void refresh(){for(PaperHost h:w.hosts)h.updateVmsProcessing(CloudSim.clock());
        Arrays.fill(auxiliaryPower,0);hardware=0;
        for(Map<String,Object> move:pending.values()){auxiliaryPower[((Host)move.get("source")).getId()]+=cfg.endpointW;auxiliaryPower[((Host)move.get("host")).getId()]+=cfg.endpointW;}
        Arrays.fill(rackPower,0);server=0;loss=0;requested=0;delivered=0;
        for(PaperHost h:w.hosts){double p=h.getPower(),extra=auxiliaryPower[h.getId()];server+=p+extra;hardware+=extra;rackPower[h.getId()/(s.hosts/s.racks)]+=p+extra;
            requested+=h.requestedMips();delivered+=h.serviceMips();double expected=0;
            for(Vm v:h.<Vm>getVmList()){double a=h.getVmScheduler().getTotalAllocatedMipsForVm(v);expected+=v.getHost()==h&&v.isInMigration()?a/.9:a;}
            cpuCheckError=Math.max(cpuCheckError,Math.abs(h.getUtilizationOfCpu()-Math.min(1,expected/s.hostMips)));
            if(hosts!=null)hosts.printf(Locale.US,"%.9f,%d,%.12f,%.9f,%.9f,%.9f,%d,%.9f%n",CloudSim.clock()-ORIGIN,h.getId(),
                    h.getUtilizationOfCpu(),h.serviceMips(),h.requestedMips(),p,h.getVmList().size(),extra);}
        for(double p:rackPower)loss+=model.loss(p);
        if(assignments!=null)for(Vm v:w.vms){PaperHost h=(PaperHost)v.getHost();assignments.printf(Locale.US,"%.9f,%d,%d,%.9f,%.9f,%.9f,%b%n",
                CloudSim.clock()-ORIGIN,v.getId(),h.getId(),w.trace[v.getId()].getUtilization(CloudSim.clock()),v.getCurrentRequestedTotalMips(),
                h.getVmScheduler().getTotalAllocatedMipsForVm(v),v.isInMigration());}
    }
    private boolean busy(Host h){for(Vm v:h.getVmList())if(v.isInMigration())return true;return false;}
    private void migrate(Map<String,Object> move){
        if(move==null||!(move.get("vm") instanceof Vm)||!(move.get("host") instanceof Host)||!(move.get("source") instanceof Host)||!(move.get("reason") instanceof String))
            throw new IllegalArgumentException("Controller plan requires vm/source/host/reason");
        Vm v=(Vm)move.get("vm");Host expectedSource=(Host)move.get("source"),destination=(Host)move.get("host");
        if(!w.vms.contains(v)||v.getHost()!=expectedSource||destination==expectedSource||destination.getId()<0||destination.getId()>=s.hosts||w.hosts.get(destination.getId())!=destination)
            throw new IllegalArgumentException("Controller proposed invalid VM ownership or migration endpoint");
        if(v.isInMigration()||pending.containsKey(v.getId())){blocked++;return;}PaperHost source=(PaperHost)v.getHost(),target=(PaperHost)move.get("host");
        double duration=v.getRam()*16000.0/s.bandwidth;
        if((busy(source)||busy(target))&&(move.get("reason").equals("framework_underload_reconstruction")||Boolean.TRUE.equals(move.get("queue")))){
            boolean exists=false;for(Map<String,Object> x:deferredUnderload)if(x.get("vm")==v)exists=true;
            if(!exists)deferredUnderload.add(move);return;
        }
        if(busy(source)||busy(target)||target.getRamProvisioner().getAvailableRam()<v.getRam()
                ||source.getBwProvisioner().getAvailableBw()<s.bandwidth/2.0
                ||target.getBwProvisioner().getAvailableBw()<v.getBw()+s.bandwidth/2.0||target.getStorage()<v.getSize()
                ||target.requestedMips()+v.getCurrentRequestedTotalMips()>Math.max(s.trigger*s.hostMips,v.getCurrentRequestedTotalMips())+1e-7
                ||target.getVmScheduler().getAvailableMips()<.1*v.getCurrentRequestedTotalMips()+1e-6
                ||source.requestedMips()<=v.getCurrentRequestedTotalMips()+1e-7&&v.getCurrentRequestedTotalMips()/s.hostMips>s.trigger){blocked++;return;}
        if(duration>=remaining()-1e-9){blocked++;return;}
        move.put("start",CloudSim.clock());move.put("source_cpu",source.getUtilizationOfCpu());
        // A VM returning to a former source must not retain that host's stale migrating-out flag.
        target.getVmScheduler().getVmsMigratingOut().remove(v.getUid());
        log("START",move);target.addMigratingInVm(v);pending.put(v.getId(),move);starts++;
        schedule(getId(),duration,FINISH,move);
    }
    private double remaining(){return ORIGIN+w.trace[0].samples.length*s.step-CloudSim.clock();}
    private void log(String event,Map<String,Object> m){if(events==null)return;Vm v=(Vm)m.get("vm");
        events.printf(Locale.US,"%.9f,%s,%d,%d,%d,%.12f,%d,%d,%s%n",CloudSim.clock()-ORIGIN,event,v.getId(),
                ((Host)m.get("source")).getId(),((Host)m.get("host")).getId(),((Number)m.get("source_cpu")).doubleValue(),v.getRam(),s.bandwidth,m.get("reason"));}
    @Override protected void processOtherEvent(SimEvent ev){
        if(ev.getTag()==TICK){advance();int index=((Integer)ev.getData()).intValue();
            if(index==w.trace[0].samples.length){ended=true;CloudSim.stopSimulation();return;}
            if(index==0)for(Cloudlet c:w.tasks)baselineMI[c.getCloudletId()]=((Simulation.OnlineScheduler)w.vms.get(c.getVmId()).getCloudletScheduler()).completedMi(c);
            for(PaperTrace t:w.trace)t.sample(index);refresh();
            for(Map<String,Object> move:w.policy.optimizeAllocation(w.vms))migrate(move);
            refresh();int active=0;for(PaperHost h:w.hosts)if(!h.getVmList().isEmpty())active++;
            if(times!=null)times.printf(Locale.US,"%d,%.9f,%.9f,%.9f,%d,%d,%d,%d,%.9f,%.9f%n",index*s.step,server,loss,server+loss,
                    active,starts,finishes,pending.size(),requested,delivered);
            samples++;schedule(getId(),s.step,TICK,Integer.valueOf(index+1));
        }else super.processOtherEvent(ev);
    }
    @Override protected void processVmMigrate(SimEvent ev,boolean ack){advance();
            @SuppressWarnings("unchecked")Map<String,Object> move=(Map<String,Object>)ev.getData();Vm v=(Vm)move.get("vm");Host target=(Host)move.get("host");
            w.policy.deallocateHostForVm(v);((Host)move.get("source")).getVmScheduler().getVmsMigratingOut().remove(v.getUid());target.removeMigratingInVm(v);
            if(!w.policy.allocateHostForVm(v,target))throw new IllegalStateException("Migration destination allocation failed VM "+v.getId());
            v.setInMigration(false);pending.remove(v.getId());finishes++;log("FINISH",move);w.policy.completed(v,(Host)move.get("source"),target,CloudSim.clock());refresh();
            List<Map<String,Object>> waiting=new ArrayList<>(deferredUnderload);deferredUnderload.clear();
            for(Map<String,Object> next:waiting)migrate(next);refresh();
        if(ack)sendNow(ev.getSource(),CloudSimTags.VM_CREATE_ACK,new int[]{getId(),v.getId(),CloudSimTags.TRUE});
    }
    public double kwh(){return(serverJ+upsJ)/3600000;}
    @Override public double getPower(){return serverJ+upsJ;} // PowerDatacenter's historical API returns accumulated W*s.
    public double[] getRackPower(){return rackPower.clone();}
    public double[] getHostPower(){double[] p=new double[w.hosts.size()];for(int i=0;i<p.length;i++)p[i]=w.hosts.get(i).getPower()+auxiliaryPower[i];return p;}
    public void close(){for(PrintWriter out:new PrintWriter[]{times,segments,events,hosts,assignments})if(out!=null){out.flush();if(out.checkError())throw new IllegalStateException("CSV output failed");out.close();}}
    public static void main(String[] args) throws Exception {ResearchRun.main(new String[]{"--test"});}
}
