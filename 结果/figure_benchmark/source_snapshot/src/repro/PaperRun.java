package repro;
import java.util.*;
import java.io.*;
import java.nio.file.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.core.CloudSim;

/** Real CloudSim bootstrap and open-service trace workload. */
public final class PaperRun {
    private PaperRun(){}
    public static final class ResidentVm extends Vm {
        private final PaperTrace trace;
        ResidentVm(int id,int user,PaperSettings s,PaperTrace trace){super(id,user,s.vmMips(id),1,s.vmRam,1000,1000,"Xen",new Simulation.OnlineScheduler(s.vmMips(id)));this.trace=trace;}
        @Override public List<Double> getCurrentRequestedMips(){return Arrays.asList(getMips()*trace.getUtilization(CloudSim.clock()));}
        @Override public int getCurrentRequestedRam(){return getRam();}
        @Override public long getCurrentRequestedBw(){return getBw();}
    }
    public static final class Workload {
        public final List<PaperHost> hosts=new ArrayList<>();public final List<Vm> vms=new ArrayList<>();
        public final List<Cloudlet> tasks=new ArrayList<>();public final PaperTrace[] trace;
        public DatacenterBroker broker;public final PowerEfficiencyAwarePolicy policy;
        Workload(double[][] raw,PaperSettings s,String method,long seed) throws Exception {
            CloudSim.init(1,Calendar.getInstance(TimeZone.getTimeZone("UTC")),false);Log.disable();
            for(int i=0;i<s.hosts;i++)hosts.add(new PaperHost(i,s));
            policy=new PowerEfficiencyAwarePolicy(hosts,s,method,seed);
            trace=new PaperTrace[raw.length];
            for(int i=0;i<raw.length;i++){
                if(raw[i].length!=raw[0].length)throw new IllegalArgumentException("Ragged trace");trace[i]=new PaperTrace(raw[i]);
            }
        }
        public void initializeBroker(PaperSettings s) throws Exception {
            broker=new DatacenterBroker("TraceBroker");
            for(int i=0;i<trace.length;i++){
                Vm vm=new ResidentVm(i,broker.getId(),s,trace[i]);vms.add(vm);
                Cloudlet c=new Cloudlet(i,1000000000000L,1,0,0,trace[i],new UtilizationModelNull(),new UtilizationModelNull());
                c.setUserId(broker.getId());c.setVmId(i);tasks.add(c);
            }
        }
        public double[] initialDemand(PaperSettings s){double[] d=new double[trace.length];for(int i=0;i<d.length;i++)d[i]=trace[i].samples[0]*s.vmMips(i)/s.hostMips;return d;}
        public void submit(){broker.submitVmList(vms);broker.submitCloudletList(tasks);}
    }
    public static PowerSupplyAwareDataCenter run(double[][] raw,PaperSettings s,String method,long seed,int[] fixed,Path prefix,boolean detailed) throws Exception {
        if(raw.length==0||raw[0].length==0)throw new IllegalArgumentException("Empty trace");Workload w=new Workload(raw,s,method,seed);
        try(PowerSupplyAwareDataCenter dc=new PowerSupplyAwareDataCenter(w,s,prefix,detailed)){
            w.initializeBroker(s);
            double[] d=w.initialDemand(s);double cap=Math.max(s.packingCap,Arrays.stream(d).max().getAsDouble());
            int[] initial=fixed!=null?fixed:method.equals("PEA-FF")?PaperPlacement.peaFirstFit(d,new SupplyPowerModel(s),cap):
                    PaperPlacement.solve(method,d,s.hosts,s.racks,new SupplyPowerModel(s),seed,s.generations,cap).host;
            w.policy.initial(initial);w.submit();if(prefix!=null)s.save(Paths.get(prefix+"_settings.properties"));
            CloudSim.startSimulation();CloudSim.stopSimulation();
            if(!dc.ended||dc.samples!=raw[0].length||w.broker.getVmsCreatedList().size()!=raw.length||dc.starts!=dc.finishes||dc.cpuCheckError>1e-7)
                throw new AssertionError("DataCenter mismatch samples="+dc.samples+" migration="+dc.starts+"/"+dc.finishes);
            if(prefix!=null)try(PrintWriter out=new PrintWriter(prefix+"_cloudlets.csv","UTF-8")){
                out.println("cloudlet_id,vm_id,dc_id,exec_start,exec_finish,exec_time,status,completed_mi");
                for(Cloudlet c:w.tasks)out.printf(Locale.US,"%d,%d,%d,%.9f,%s,%s,%s,%d%n",c.getCloudletId(),c.getVmId(),dc.getId(),c.getExecStartTime(),
                        c.getCloudletStatus()==Cloudlet.SUCCESS?String.valueOf(c.getFinishTime()):"NA",
                        c.getCloudletStatus()==Cloudlet.SUCCESS?String.valueOf(c.getActualCPUTime()):"NA",c.getCloudletStatusString(),
                        ((Simulation.OnlineScheduler)w.vms.get(c.getVmId()).getCloudletScheduler()).completedMi(c)-dc.baselineMI[c.getCloudletId()]);}
            return dc;
        }
    }
    public static void main(String[] args) throws Exception {
        PaperSettings s=new PaperSettings(Paths.get("paper_alignment/config/platform.properties"));
        double[][] raw={{.2,.4},{.3,.1}};int[] fixed={0,0};
        PowerSupplyAwareDataCenter a=run(raw,s,"BFD",101,fixed,Paths.get("paper_alignment/results/test_nomigration"),true);
        SupplyPowerModel m=new SupplyPowerModel(s);
        double expected=(m.powers(new double[]{.2,.3},fixed)[2]+m.powers(new double[]{.4,.1},fixed)[2])*300/3600000;
        SupplyPowerModel.close(a.kwh(),expected);if(a.starts!=0)throw new AssertionError("none controller migrated");
        PaperSettings dynamic=s.with("controller","threshold").with("packing.cap",".9");double[][] t={{.4,.6,.1},{.4,.5,.1}};
        PowerSupplyAwareDataCenter b=run(t,dynamic,"BFD-GA",101,fixed,Paths.get("paper_alignment/results/test_migration"),true);
        if(b.starts!=1||b.finishes!=1||b.migrationSeconds<8)throw new AssertionError("Timed migration failed "+b.starts);
        PowerSupplyAwareDataCenter fast=run(t,dynamic.with("host.bandwidth.kbps","10000000"),"BFD-GA",101,fixed,null,false);
        if(fast.migrationSeconds>=b.migrationSeconds)throw new AssertionError("Bandwidth monotonicity");
        PaperSettings edge=dynamic.with("vm.ram.mb","18750");
        PowerSupplyAwareDataCenter cutoff=run(new double[][]{{.4,.6},{.4,.5}},edge,"BFD",101,fixed,null,false);
        if(cutoff.starts!=0)throw new AssertionError("Migration completing exactly at window end was not rejected");
        SupplyPowerModel.close(b.getPower(),b.kwh()*3600000);
        System.out.println("PASS exact no-migration integral, one VM trigger, timed start/finish, faster bandwidth");
    }
}
