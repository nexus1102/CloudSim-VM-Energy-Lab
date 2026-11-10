package repro;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Platform, paper-trigger dynamics, explicit sensitivities, static and convergence cases. */
public final class PaperExperiments {
    private static final Path ROOT=Paths.get("paper_alignment");
    private static final Set<String> DONE=new HashSet<>();
    private static PrintWriter output(String name,String header) throws Exception{PrintWriter o=new PrintWriter(ROOT.resolve("results/"+name).toFile(),"UTF-8");o.println(header);return o;}
    private static void dynamic(PrintWriter out,String caseName,double[][] raw,PaperSettings s,String method,long seed,boolean detail) throws Exception {
        if(raw.length!=100||raw[0].length!=288)throw new IllegalArgumentException("Dynamic case "+caseName+" must be 100 VMs x 288 samples");
        String id=caseName+","+method+","+seed;if(DONE.contains(id))return;
        Path prefix=ROOT.resolve("results/"+caseName+"_"+method+"_"+seed);
        PowerSupplyAwareDataCenter dc=PaperRun.run(raw,s,method,seed,null,prefix,detail);
        double mean=0;for(double[] row:raw)for(double x:row)mean+=x/(raw.length*raw[0].length);
        out.printf(Locale.US,"%s,%s,%d,%.12f,%.9f,%.9f,%.9f,%d,%d,%d,%.9f,%.9f,%.9f,%.9f%n",caseName,method,seed,mean,
                dc.serverJ/3600000,dc.upsJ/3600000,dc.kwh(),dc.starts,dc.finishes,dc.blocked,
                dc.requestedMI,dc.deliveredMI,dc.migrationSeconds,dc.cpuCheckError);out.flush();
        System.out.printf(Locale.US,"%s %s seed%d %.3fkWh migrations=%d shortage=%.4f%%%n",caseName,method,seed,dc.kwh(),dc.starts,
                100*(dc.requestedMI-dc.deliveredMI)/dc.requestedMI);
    }
    private static void platform(PaperSettings s) throws Exception {
        double[][] raw=Simulation.read(ROOT.resolve("inputs/platform_raw.csv"));
        if(raw.length!=20||raw[0].length!=288)throw new IllegalArgumentException("Platform validation requires 20 VMs x 288 samples");
        PaperRun.run(raw,s,"fixed_layout",101,SupplyPowerModel.figure14(),ROOT.resolve("results/platform_fixed"),true);
        PaperRun.run(raw,s,"PEA-FF",101,null,ROOT.resolve("results/platform_peaff"),true);
    }
    private static void dynamics(PaperSettings s,boolean resume) throws Exception {
        Path summary=ROOT.resolve("results/dynamic_summary.csv");List<String> old=new ArrayList<>();
        if(resume&&Files.exists(summary)){for(String line:Files.readAllLines(summary))if(!line.startsWith("case,")&&!line.trim().isEmpty()){
            String[] f=line.split(",");if(f.length!=14)throw new IllegalStateException("Corrupt resume summary");
            DONE.add(f[0]+","+f[1]+","+f[2]);old.add(line);}}
        try(PrintWriter out=output("dynamic_summary.csv","case,method,seed,mean_vm_cpu,server_kwh,ups_kwh,total_kwh,started,finished,blocked,requested_mi,delivered_mi,migration_seconds,cpu_error")){
            for(String line:old)out.println(line);out.flush();
            double[][] main=Simulation.read(Paths.get("correction/inputs/cohort25_20110303.csv"));
            for(String method:PaperPlacement.METHODS)for(int k=0;k<30;k++)dynamic(out,"main",main,s,method,101+101*k,k==0);
            for(String day:CorrectedExperiments.DAYS)for(String cohort:new String[]{"random","cohort25"}){
                if(day.equals("20110303")&&cohort.equals("cohort25"))continue;
                double[][] raw=Simulation.read(Paths.get("correction/inputs/"+cohort+"_"+day+".csv"));
                for(String method:PaperPlacement.METHODS)dynamic(out,cohort+"_"+day,raw,s,method,101,false);
            }
            for(String sensitivity:new String[]{"server_objective","uniform_vm","bandwidth10G","periodic_extension"}){
                PaperSettings c=sensitivity.equals("server_objective")?s.with("genetic.objective","server_only"):
                        sensitivity.equals("uniform_vm")?s.with("vm.mips","2500"):
                        sensitivity.equals("bandwidth10G")?s.with("host.bandwidth.kbps","10000000"):s.with("controller","periodic_extension");
                for(String method:PaperPlacement.METHODS)for(int k=0;k<(sensitivity.equals("periodic_extension")?1:3);k++)
                    dynamic(out,sensitivity,main,c,method,101+101*k,k==0&&method.equals("BFD-GA"));
            }
        }
    }
    private static void statics(PaperSettings base) throws Exception {
        try(PrintWriter out=output("static_summary.csv","family,architecture,target,actual_host_demand,actual_vm_cpu,vm_count,method,seed,hosts,server_w,ups_w,total_w,solve_ms,idle_w,max_w,ups_usable_w,ups_factor,ups_a0,ups_a1,ups_a2,rack0_output_w,rack1_output_w,rack2_output_w,rack3_output_w,rack4_output_w")){
            for(String family:new String[]{"physical_host_load","vm_average_cpu"})for(String arch:Experiments.ARCH)for(int level=10;level<=70;level+=10){
                PaperSettings s=base.with("controller","none").with("packing.cap","1").with("ups.factor",arch.startsWith("2N")?"2":"1.25");
                if(arch.endsWith("AC"))s=s.with("ups.a0",".0376").with("ups.a1",".0069").with("ups.a2",".0319");
                double[][] raw=Simulation.read(family.equals("physical_host_load")?Paths.get("correction/inputs/static_"+level+".csv"):ROOT.resolve("inputs/vm_average_"+level+".csv"));
                double[] d=new double[raw.length];double physical=0,vm=0;for(int i=0;i<d.length;i++){d[i]=raw[i][0]*s.vmMips(i)/s.hostMips;physical+=d[i];vm+=raw[i][0];}
                SupplyPowerModel model=new SupplyPowerModel(s);
                for(String method:PaperPlacement.METHODS)for(long seed:Experiments.SEEDS){
                    PaperPlacement.Answer answer=PaperPlacement.solve(method,d,s.hosts,s.racks,model,seed,s.generations,1);
                    PowerSupplyAwareDataCenter dc=PaperRun.run(raw,s,method,seed,answer.host,null,false);
                    out.printf(Locale.US,"%s,%s,%.2f,%.9f,%.9f,%d,%s,%d,%d,%.9f,%.9f,%.9f,%.6f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f",family,arch,level/100.,physical/s.hosts,vm/raw.length,
                            raw.length,method,seed,PaperPlacement.count(answer.host),dc.serverJ/s.step,dc.upsJ/s.step,(dc.serverJ+dc.upsJ)/s.step,answer.nanos/1e6,
                            s.idle,s.max,s.rated,s.factor,s.a0,s.a1,s.a2);
                    for(double rack:dc.getRackPower())out.printf(Locale.US,",%.9f",rack);out.println();out.flush();
                }System.out.println("static "+family+" "+arch+" "+level+"% complete");
            }
        }
    }
    private static void performance(PaperSettings s) throws Exception {
        try(PrintWriter out=output("performance.csv","vm_count,budget,method,seed,total_w,reference_w,within_1pct,solve_ms")){
            SupplyPowerModel model=new SupplyPowerModel(s);
            for(int n:new int[]{5,10,12,30,40,80,150,230,288}){
                Random rng=new Random(72+n);double[] d=new double[n];for(int i=0;i<n;i++)d[i]=.05+.4*rng.nextDouble();
                PaperPlacement.Answer reference=PaperPlacement.solve("BFD-GA",d,100,5,model,101,60,1);
                double ref=model.powers(d,reference.host)[2];
                for(int budget:new int[]{3,6,12,28,45,59})for(String method:new String[]{"GA","BFD-GA"})for(long seed:Experiments.SEEDS){
                    PaperPlacement.Answer a=PaperPlacement.solve(method,d,100,5,model,seed,budget,1);double total=model.powers(d,a.host)[2];
                    out.printf(Locale.US,"%d,%d,%s,%d,%.9f,%.9f,%b,%.6f%n",n,budget,method,seed,total,ref,total<=ref*1.01+1e-8,a.nanos/1e6);
                }out.flush();
            }
        }
    }
    private static void framework(PaperSettings s) throws Exception {
        Path path=ROOT.resolve("results/dynamic_summary.csv");List<String> old=Files.readAllLines(path);
        try(PrintWriter out=output("dynamic_summary.csv",old.get(0))){for(int i=1;i<old.size();i++)if(!old.get(i).startsWith("framework_"))out.println(old.get(i));
            double[][] raw=Simulation.read(Paths.get("correction/inputs/cohort25_20110303.csv"));
            PaperSettings framework=s.with("controller","framework_underload");
            for(String method:PaperPlacement.METHODS)for(int k=0;k<30;k++)dynamic(out,"framework_underload",raw,framework,method,101+101*k,k==0);
            for(String day:CorrectedExperiments.DAYS)for(String cohort:new String[]{"random","cohort25"}){
                if(day.equals("20110303")&&cohort.equals("cohort25"))continue;
                double[][] daily=Simulation.read(Paths.get("correction/inputs/"+cohort+"_"+day+".csv"));
                for(String method:PaperPlacement.METHODS)dynamic(out,"framework_"+cohort+"_"+day,daily,framework,method,101,false);
            }
        }
    }
    public static void main(String[] args) throws Exception {
        Files.createDirectories(ROOT.resolve("results"));PaperSettings s=new PaperSettings(ROOT.resolve("config/main.properties"));
        if(s.hosts!=100||s.racks!=5||s.step!=300)throw new IllegalArgumentException("Published experiment family requires 100 Hosts, 5 racks and 300-second PlanetLab samples");
        if(Arrays.asList(args).contains("--resume"))throw new IllegalArgumentException("Resume disabled: rerun to avoid mixing different runtime parameters or source revisions");
        if(Arrays.asList(args).contains("--framework-only")){framework(s);return;}
        if(Arrays.asList(args).contains("--dynamic-only")){dynamics(s,Arrays.asList(args).contains("--resume"));return;}
        if(Arrays.asList(args).contains("--static-only")){statics(s);performance(s);return;}
        platform(new PaperSettings(ROOT.resolve("config/platform.properties")));dynamics(s,false);statics(s);performance(s);framework(s);
        System.out.println("PASS paper-aligned platform, dynamics, static cases and explicit convergence criterion");
    }
}
