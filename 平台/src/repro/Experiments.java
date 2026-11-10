package repro;

import java.util.*;
import java.io.*;
import java.nio.file.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.core.CloudSim;
import org.cloudbus.cloudsim.provisioners.*;

/** Full static, dynamic, platform-validation and convergence experiments. */
public final class Experiments {
    public static final long[] SEEDS={101,202,303,404,505};
    public static final String[] ARCH={"N+1AC","N+1DC","2NAC","2NDC"};
    private Experiments() { }
    private static PrintWriter csv(String name,String header) throws Exception {
        PrintWriter out=new PrintWriter("results/"+name+".csv","UTF-8"); out.println(header); return out;
    }
    private static double[][] constant(double[] d) {
        double[][] t=new double[d.length][1]; for (int i=0;i<d.length;i++) t[i][0]=d[i]; return t;
    }
    private static void completedCloudletSmoke() throws Exception {
        CloudSim.init(1,Calendar.getInstance(TimeZone.getTimeZone("UTC")),false); Log.disable();
        List<Pe> pes=Arrays.asList(new Pe(0,new PeProvisionerSimple(2500)));
        Host host=new Host(0,new RamProvisionerSimple(4096),new BwProvisionerSimple(10000),1000000,pes,new VmSchedulerTimeShared(pes));
        List<Host> hs=Arrays.asList(host);
        new Datacenter("CompleteSmoke",new DatacenterCharacteristics("x86","Linux","Xen",hs,8,0,0,0,0),
                new VmAllocationPolicySimple(hs),new LinkedList<Storage>(),0);
        DatacenterBroker b=new DatacenterBroker("SmokeBroker");
        Vm vm=new Vm(0,b.getId(),2500,1,512,1000,1000,"Xen",new CloudletSchedulerTimeShared());
        UtilizationModel full=new UtilizationModelFull();
        Cloudlet c=new Cloudlet(0,2500,1,0,0,full,full,full); c.setUserId(b.getId()); c.setVmId(0);
        b.submitVmList(Arrays.asList(vm)); b.submitCloudletList(Arrays.asList(c)); CloudSim.startSimulation(); CloudSim.stopSimulation();
        if (b.getCloudletReceivedList().size()!=1 || c.getCloudletStatus()!=Cloudlet.SUCCESS)
            throw new AssertionError("Cloudlet completion smoke failed");
        PowerModels.close(c.getActualCPUTime(),1);
        try (PrintWriter out=csv("received_cloudlets","cloudlet_id,vm_id,dc_id,exec_start,exec_finish,exec_time,status")) {
            out.printf(Locale.US,"%d,%d,%d,%.6f,%.6f,%.6f,SUCCESS%n",c.getCloudletId(),c.getVmId(),c.getResourceId(),
                    c.getExecStartTime(),c.getFinishTime(),c.getActualCPUTime());
        }
    }
    private static void validation(double[][] raw) throws Exception {
        double[][] trace=new double[20][]; int[] plan={5,5,5,5,0,0,0,0,1,1,1,0,1,6,5,6,6,6,6,7};
        for (int i=0;i<20;i++) trace[i]=raw[i].clone();
        for (int h=0;h<10;h++) {
            double max=0;
            for (int t=0;t<288;t++) { double total=0;
                for (int i=0;i<20;i++) if (plan[i]==h) total+=trace[i][t]; max=Math.max(max,total); }
            double scale=max>0?.98/max:1;
            for (int i=0;i<20;i++) if (plan[i]==h) for (int t=0;t<288;t++) trace[i][t]*=scale;
        }
        PowerModels.Ups literal=new PowerModels.Ups(2000,.0241,.0353,.0617,1);
        Simulation.Stats s=Simulation.run(trace,plan,10,2,literal,"PEA-FF-reference-layout",101,false,Paths.get("results/validation"));
        try (PrintWriter out=csv("validation_vm","time_s,vm_id,host_id,cpu")) {
            for (int t=0;t<288;t++) for (int i=0;i<20;i++)
                out.printf(Locale.US,"%d,%d,%d,%.12f%n",t*300,i+1,plan[i],trace[i][t]);
        }
        try (PrintWriter out=csv("verification","check,value,limit")) {
            out.printf(Locale.US,"platform_cpu_max_error,%.12g,1e-8%n",s.cpuError);
            out.printf(Locale.US,"platform_power_max_error_w,%.12g,1e-5%n",s.powerError);
            out.println("platform_samples,"+s.samples+",288"); out.println("platform_vm_created,"+s.created+",20");
        }
        // This run verifies the depicted fixed layout. Original PEA-FF details are absent.
        System.out.println("Platform validation completed (literal Table 2-6)");
    }
    private static void statics(double[][] staticData) throws Exception {
        try (PrintWriter out=csv("static","architecture,load,method,seed,hosts,server_w,ups_loss_w,total_w,solve_ms,cpu_error,power_error_w");
                PrintWriter placements=csv("static_placements","architecture,load,method,seed,vm_id,host_id,cpu");
                PrintWriter histories=csv("convergence","architecture,load,method,seed,generation,objective_w")) {
            for (String arch:ARCH) for (int l=0;l<7;l++) for (String method:Placement.METHODS) for (long seed:SEEDS) {
                double[] d=staticData[l]; PowerModels.Ups ups=PowerModels.model(arch);
                Placement.Answer a=Placement.solve(method,d,100,5,ups,seed,Placement.GENERATIONS,1);
                Simulation.Stats s=Simulation.run(constant(d),a.host,100,5,ups,method,seed,false,null);
                double server=s.serverKwh*3600000/300,loss=s.upsKwh*3600000/300;
                out.printf(Locale.US,"%s,%.1f,%s,%d,%d,%.9f,%.9f,%.9f,%.6f,%.12g,%.12g%n",
                        arch,(l+1)/10.,method,seed,Placement.count(a.host),server,loss,server+loss,a.nanos/1e6,s.cpuError,s.powerError);
                for (int i=0;i<d.length;i++) placements.printf(Locale.US,"%s,%.1f,%s,%d,%d,%d,%.12f%n",arch,(l+1)/10.,method,seed,i,a.host[i],d[i]);
                for (int g=0;g<a.history.length;g++) histories.printf(Locale.US,"%s,%.1f,%s,%d,%d,%.9f%n",arch,(l+1)/10.,method,seed,g,a.history[g]);
            }
        }
        System.out.println("Static experiments completed: 700 CloudSim runs");
    }
    private static void dynamics(double[][] trace) throws Exception {
        double[] first=new double[trace.length]; for (int i=0;i<first.length;i++) first[i]=trace[i][0];
        PowerModels.Ups ups=PowerModels.model("N+1DC");
        try (PrintWriter out=csv("dynamic_summary","method,seed,server_kwh,ups_kwh,total_kwh,migrations,cpu_error,power_error_w,samples")) {
            for (String method:Placement.METHODS) for (long seed:SEEDS) {
                Placement.Answer a=Placement.solve(method,first,100,5,ups,seed,Placement.GENERATIONS,.9);
                Simulation.Stats s=Simulation.run(trace,a.host,100,5,ups,method,seed,true,
                        Paths.get("results/dynamic_"+method+"_"+seed));
                out.printf(Locale.US,"%s,%d,%.9f,%.9f,%.9f,%d,%.12g,%.12g,%d%n",
                        method,seed,s.serverKwh,s.upsKwh,s.totalKwh(),s.migrations,s.cpuError,s.powerError,s.samples);
                out.flush(); System.out.printf(Locale.US,"Dynamic %s seed=%d %.3f kWh migrations=%d%n",method,seed,s.totalKwh(),s.migrations);
            }
        }
    }
    private static void performance() throws Exception {
        int[] budgets={3,6,12,28,45,59},sizes={5,10,12,30,40,80,150,230,288};
        PowerModels.Ups ups=PowerModels.model("N+1DC");
        try (PrintWriter out=csv("performance","budget,vm_count,method,seed,hosts,bfd_hosts,total_w,lower_bound_w,relative_gap,success,solve_ms")) {
            for (int n:sizes) {
                Random r=new Random(72+n); double[] d=new double[n]; double total=0;
                for (int i=0;i<n;i++) { d[i]=.05+.4*r.nextDouble(); total+=d[i]; }
                int[] bfd=Placement.greedy(d,100,true,1); int bins=Placement.count(bfd);
                double server=bins*PowerModels.IDLE+(PowerModels.MAX-PowerModels.IDLE)*total;
                // Lower bound conditional on BFD's fixed group count; convex UPS loss minimized at equal rack loads.
                double bound=server+5*ups.loss(server/5);
                for (int budget:budgets) for (String m:new String[]{"GA","BFD-GA"}) for (long seed:SEEDS) {
                    Placement.Answer a=Placement.solve(m,d,100,5,ups,seed,budget,1);
                    double power=PowerModels.powers(d,a.host,100,5,ups)[2],gap=(power-bound)/bound;
                    boolean success=Placement.count(a.host)<=bins && gap<=.01+1e-8;
                    out.printf(Locale.US,"%d,%d,%s,%d,%d,%d,%.9f,%.9f,%.9f,%s,%.6f%n",budget,n,m,seed,
                            Placement.count(a.host),bins,power,bound,gap,success,a.nanos/1e6);
                }
            }
        }
        System.out.println("Convergence benchmark completed; success criterion explicitly defined");
    }
    private static void sensitivity(double[][] staticData) throws Exception {
        try (PrintWriter out=csv("sensitivity","coefficient_source,rated_w,factor,load,bfd_total_w,proposed_total_w,reduction_pct")) {
            for (String source:new String[]{"table2-6","figure2-5AC","figure2-5DC"})
              for (double rated:new double[]{7000,10000,14000}) for (double factor:new double[]{1,1.25,2}) for (int l:new int[]{1,2,4}) {
                PowerModels.Ups base=PowerModels.model(source.endsWith("DC")?"N+1DC":"N+1AC");
                PowerModels.Ups ups=source.equals("table2-6")?new PowerModels.Ups(rated,.0241,.0353,.0617,factor)
                        :new PowerModels.Ups(rated,base.a0,base.a1,base.a2,factor);
                double[] d=staticData[l]; int[] bfd=Placement.greedy(d,100,true,1);
                Placement.Answer a=Placement.solve("BFD-GA",d,100,5,ups,101,60,1);
                double pb=PowerModels.powers(d,bfd,100,5,ups)[2],pa=PowerModels.powers(d,a.host,100,5,ups)[2];
                out.printf(Locale.US,"%s,%.0f,%.2f,%.1f,%.9f,%.9f,%.9f%n",source,rated,factor,(l+1)/10.,pb,pa,100*(pb-pa)/pb);
            }
        }
    }
    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US); Files.createDirectories(Paths.get("results"));
        double[][] raw=Simulation.read(Paths.get("data/raw_matrix.csv"));
        double[][] trace=Simulation.read(Paths.get("data/dynamic.csv"));
        double[][] staticData=Simulation.read(Paths.get("data/static.csv"));
        if (raw.length!=100 || trace.length!=100 || trace[0].length!=288 || staticData.length!=7 || staticData[0].length!=100)
            throw new IllegalArgumentException("Expected 100x288 dynamic and 7x100 static data");
        double mean=0; for (double[] row:trace) for (double x:row) mean+=x/(100*288.);
        PowerModels.close(mean,.25);
        PowerModels.main(new String[0]); Placement.main(new String[0]); Simulation.main(new String[0]);
        completedCloudletSmoke(); validation(raw); statics(staticData); dynamics(trace); performance(); sensitivity(staticData);
        System.out.println("ALL EXPERIMENTS PASSED");
    }
}
