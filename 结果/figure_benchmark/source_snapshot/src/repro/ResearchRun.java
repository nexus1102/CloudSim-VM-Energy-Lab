package repro;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.core.CloudSim;

/** Real CloudSim execution with configured modular supply and independently auditable work. */
public final class ResearchRun {
    public static final class ResidentVm extends Vm {
        private final PaperTrace trace;private final double snap;
        ResidentVm(int id,int user,PaperSettings s,PaperTrace trace){
            super(id,user,s.vmMips(id),1,s.vmRam,1000,1000,"Xen",new Simulation.OnlineScheduler(s.vmMips(id)));
            this.trace=trace;snap=Double.parseDouble(s.values.getProperty("scheduler.request.snap.epsilon.mips","1e-8"));
        }
        @Override public List<Double> getCurrentRequestedMips(){double raw=getMips()*trace.getUtilization(CloudSim.clock()),nearest=Math.rint(raw);
            return Arrays.asList(Math.abs(raw-nearest)<=snap?nearest:raw);}
        @Override public int getCurrentRequestedRam(){return getRam();}
        @Override public long getCurrentRequestedBw(){return getBw();}
    }
    public static final class Workload {
        public final List<PaperHost> hosts=new ArrayList<>();public final List<Vm> vms=new ArrayList<>();
        public final List<Cloudlet> tasks=new ArrayList<>();public final PaperTrace[] trace;
        public final ResearchPolicy policy;public DatacenterBroker broker;
        Workload(double[][] raw,ResearchConfig cfg,long seed)throws Exception {
            PaperSettings s=cfg.settings;CloudSim.init(1,Calendar.getInstance(TimeZone.getTimeZone("UTC")),false);Log.disable();
            for(int i=0;i<s.hosts;i++)hosts.add(new PaperHost(i,s));policy=new ResearchPolicy(hosts,cfg,seed);trace=new PaperTrace[raw.length];
            for(int i=0;i<raw.length;i++){if(raw[i].length!=raw[0].length)throw new IllegalArgumentException("Ragged CPU trace");trace[i]=new PaperTrace(raw[i]);}
        }
        void broker(PaperSettings s)throws Exception {
            broker=new DatacenterBroker("ResearchTraceBroker");
            for(int i=0;i<trace.length;i++){
                Vm vm=new ResidentVm(i,broker.getId(),s,trace[i]);vms.add(vm);
                Cloudlet c=new Cloudlet(i,1000000000000L,1,0,0,trace[i],new UtilizationModelNull(),new UtilizationModelNull());
                c.setUserId(broker.getId());c.setVmId(i);tasks.add(c);
            }
        }
    }
    public static ResearchDatacenter run(double[][] raw,ResearchConfig cfg,String method,long seed,int[] fixed,Path prefix,boolean detailed)throws Exception {
        if(raw.length==0||raw[0].length==0)throw new IllegalArgumentException("Empty CPU trace");PaperSettings s=cfg.settings;
        Workload w=new Workload(raw,cfg,seed);
        try(ResearchDatacenter dc=new ResearchDatacenter(w,cfg,prefix,detailed)) {
            w.broker(s);double[] d=new double[raw.length];for(int i=0;i<d.length;i++)d[i]=raw[i][0]*s.vmMips(i)/s.hostMips;
            int[] initial=fixed==null?ResearchPlacement.solve(method,d,s.hosts,s.racks,new SupplyPowerModel(s),seed,s.generations,s.packingCap,cfg.bfdSeed).host:fixed.clone();
            if(initial.length!=raw.length)throw new IllegalArgumentException("Mapping must include each VM exactly once");
            for(double u:ResearchPlacement.loads(d,initial,s.hosts))if(u>s.packingCap+1e-8)throw new IllegalArgumentException("Initial mapping exceeds configured CPU cap");
            w.policy.initial(initial);w.broker.submitVmList(w.vms);w.broker.submitCloudletList(w.tasks);
            if(prefix!=null){s.save(Paths.get(prefix+"_settings.properties"));cfg.save(Paths.get(prefix+"_research.properties"));
                try(PrintWriter out=new PrintWriter(prefix+"_initial.csv","UTF-8")){
                    out.println("vm_id,raw_cpu,normalized_demand,host_id");
                    for(int i=0;i<d.length;i++)out.printf(Locale.US,"%d,%.12f,%.12f,%d%n",i,raw[i][0],d[i],initial[i]);
                    if(out.checkError())throw new IOException("Initial mapping write failed");
                }
            }
            CloudSim.startSimulation();CloudSim.stopSimulation();
            if(dc.failure!=null)throw dc.failure;
            if(!dc.ended||dc.samples!=raw[0].length||w.broker.getVmsCreatedList().size()!=raw.length||dc.starts!=dc.finishes||dc.cpuCheckError>1e-7)
                throw new AssertionError("Research execution mismatch samples="+dc.samples+" migrations="+dc.starts+"/"+dc.finishes);
            if(prefix!=null)try(PrintWriter out=new PrintWriter(prefix+"_cloudlets.csv","UTF-8")){
                out.println("cloudlet_id,vm_id,dc_id,exec_start,exec_finish,exec_time,status,completed_mi");
                for(Cloudlet c:w.tasks)out.printf(Locale.US,"%d,%d,%d,%.9f,NA,NA,%s,%d%n",c.getCloudletId(),c.getVmId(),dc.getId(),c.getExecStartTime(),c.getCloudletStatusString(),
                        ((Simulation.OnlineScheduler)w.vms.get(c.getVmId()).getCloudletScheduler()).completedMi(c)-dc.baselineMI[c.getCloudletId()]);
            }
            return dc;
        }
    }
    public static final class InvalidController implements ResearchPolicy.Controller {
        public List<Map<String,Object>> propose(List<? extends Vm> v,List<? extends Host> h,ResearchConfig c){
            Map<String,Object> m=new HashMap<>();m.put("vm",v.get(0));m.put("source",v.get(0).getHost());m.put("host",v.get(0).getHost());m.put("reason","custom");return Arrays.asList(m);
        }
    }
    public static final class SerialController implements ResearchPolicy.Controller {
        private boolean done;
        public List<Map<String,Object>> propose(List<? extends Vm> v,List<? extends Host> h,ResearchConfig c){
            if(done)return Collections.emptyList();done=true;List<Map<String,Object>> result=new ArrayList<>();
            for(int i=0;i<2;i++){Map<String,Object> m=new HashMap<>();m.put("vm",v.get(i));m.put("source",v.get(i).getHost());
                m.put("host",h.get(i+1));m.put("reason","custom_serial");m.put("queue",true);result.add(m);}
            return result;
        }
    }
    public static void main(String[] args)throws Exception {
        ResearchConfig c=new ResearchConfig(Paths.get("research_platform/config/default.properties")).with("research.controller","none").with("vm.mips","2500");
        double[][] small={{.2,.4},{.3,.1}};int[] fixed={0,0};SupplyPowerModel model=new SupplyPowerModel(c.settings);
        ResearchDatacenter a=run(small,c,"BFD",101,fixed,null,false);
        double expected=(model.powers(new double[]{.2,.3},fixed)[2]+model.powers(new double[]{.4,.1},fixed)[2])*300/3600000;
        SupplyPowerModel.close(a.kwh(),expected);
        c=c.with("research.controller","threshold");double[][] peak={{.4,.6,.1},{.4,.5,.1}};
        ResearchDatacenter zero=run(peak,c,"BFD",101,fixed,null,false);
        ResearchDatacenter extra=run(peak,c.with("migration.incremental.w.per.endpoint","20"),"BFD",101,fixed,null,false);
        if(extra.starts!=1||extra.finishes!=1)throw new AssertionError("Timed migration missing");
        if(Math.abs(extra.hardwareJ-2*20*extra.migrationSeconds)>1e-7||Math.abs(extra.serverJ-zero.serverJ-extra.hardwareJ)>1e-5||extra.upsJ<=zero.upsJ)
            throw new AssertionError("Hardware/UPS energy feedback mismatch");
        try{run(peak,c.with("research.controller.class","repro.ResearchRun$InvalidController").with("research.controller","custom"),"BFD",101,fixed,null,false);
            throw new AssertionError("Invalid plugin plan accepted");}catch(IllegalArgumentException expectedError){}
        ResearchConfig exact=new ResearchConfig(Paths.get("research_platform/config/default.properties")).with("research.controller","none")
                .with("packing.cap","1").with("population","20").with("generations","30");
        ResearchDatacenter full=run(Simulation.read(Paths.get("correction/inputs/static_20.csv")),exact,"GGA",202,null,null,false);
        if(Math.abs(full.requestedMI-full.deliveredMI)>.05)throw new AssertionError("Roundoff caused artificial saturation loss");
        ResearchDatacenter serial=run(peak,c.with("research.controller.class","repro.ResearchRun$SerialController").with("research.controller","custom"),"BFD",101,fixed,null,false);
        if(serial.starts!=2||serial.finishes!=2||Math.abs(serial.migrationSeconds-16.384)>1e-7)throw new AssertionError("Custom serial plan did not finish safely");
        double[][] nic={{.2,.3,.1},{.2,.3,.1},{.2,.3,.1},{.2,.3,.1}};
        ResearchDatacenter limited=run(nic,c.with("host.bandwidth.kbps","5000").with("vm.ram.mb","1"),"BFD",101,new int[]{0,0,0,0},null,false);
        if(limited.starts!=0||limited.blocked==0)throw new AssertionError("Copy bandwidth exceeded reserved VM traffic capacity");
        System.out.println("PASS actual CloudSim events, exact no-migration integral, incremental hardware plus UPS energy, and invalid custom plan rejection");
    }
}
