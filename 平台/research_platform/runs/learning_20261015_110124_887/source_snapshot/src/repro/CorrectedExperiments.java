package repro;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Immutable raw-trace replay and controlled diagnosis of the Figure 2-24 mismatch. */
public final class CorrectedExperiments {
    public static final Path ROOT=Paths.get("correction");
    public static final String[] DAYS={"20110303","20110306","20110309","20110322","20110325",
            "20110403","20110409","20110411","20110412","20110420"};
    public static final long[] SEEDS={101,202,303,404,505};
    private static final Set<String> COMPLETED=new HashSet<>();
    private CorrectedExperiments() { }
    private static PrintWriter csv(String file,String header) throws Exception {
        PrintWriter out=new PrintWriter(ROOT.resolve("results").resolve(file).toFile(),"UTF-8");out.println(header);return out;
    }
    private static Simulation.Stats execute(double[][] trace,String caseName,String method,long seed,
            boolean heterogeneous,boolean periodic,boolean detailed,PrintWriter summary) throws Exception {
        return execute(trace,caseName,method,seed,heterogeneous,periodic,detailed,summary,false);
    }
    private static Simulation.Stats execute(double[][] trace,String caseName,String method,long seed,
            boolean heterogeneous,boolean periodic,boolean detailed,PrintWriter summary,boolean stable) throws Exception {
        if (COMPLETED.contains(caseName+","+method+","+seed)) return null;
        double[] mips=DynamicController.vmMips(trace.length,heterogeneous);
        double[] first=DynamicController.demand(trace,0,mips);
        PowerModels.Ups ups=PowerModels.model("N+1DC");
        int[] initial=Placement.solve(method,first,100,5,ups,seed,Placement.GENERATIONS,
                DynamicController.capacity(first)).host;
        Simulation.Stats stats=Simulation.run(trace,initial,100,5,ups,method,seed,true,
                ROOT.resolve("results").resolve(caseName+"_"+method+"_"+seed),new Simulation.Options(mips,periodic,detailed,stable));
        summary.printf(Locale.US,"%s,%s,%d,%s,%s,%d,%.9f,%.9f,%.9f,%.9f,%.9f,%d,%d,%d,%d,%d,%.6f,%d,%.12g,%.12g%n",
                caseName,method,seed,heterogeneous?"official_vm_types":"uniform2500",periodic?(stable?"periodic_stable":"periodic_full"):"overload_only",
                trace.length,stats.meanVmCpu/stats.samples,stats.meanPhysicalDemand/(100*stats.samples),
                stats.serverKwh,stats.upsKwh,stats.totalKwh(),stats.migrations,stats.activeStart,stats.activeEnd,
                stats.activeMin,stats.activeMax,stats.activeSum/stats.samples,stats.aboveThresholdHostSamples,stats.cpuError,stats.powerError);
        summary.flush();System.out.printf(Locale.US,"%s %s seed%d %.3fkWh hosts=%d->%d [%d,%d]%n",
                caseName,method,seed,stats.totalKwh(),stats.activeStart,stats.activeEnd,stats.activeMin,stats.activeMax);
        return stats;
    }
    private static void dynamic() throws Exception {
        List<String> preserved=new ArrayList<>();
        Path summaryPath=ROOT.resolve("results/dynamic_summary.csv");
        if (!COMPLETED.isEmpty()) for (String line:Files.readAllLines(summaryPath))
            if (!line.startsWith("case,") && !line.startsWith("ablation_") && !line.trim().isEmpty()) preserved.add(line);
        try (PrintWriter out=csv("dynamic_summary.csv","case,method,seed,resources,controller,vm_count,mean_vm_cpu,mean_physical_host_load,server_kwh,ups_kwh,total_kwh,migrations,active_start,active_end,active_min,active_max,active_mean,above_threshold_host_samples,cpu_error,power_error_w")) {
            for (String line:preserved) out.println(line);out.flush();
            double[][] main=Simulation.read(ROOT.resolve("inputs/cohort25_20110303.csv"));
            for (String method:Placement.METHODS) for (long seed:SEEDS)
                execute(main,"main",method,seed,true,true,seed==101,out);
            for (String day:DAYS) for (String cohort:new String[]{"random","cohort25"}) {
                if (day.equals("20110303") && cohort.equals("cohort25")) continue; // main seed101 covers this group.
                double[][] trace=Simulation.read(ROOT.resolve("inputs").resolve(cohort+"_"+day+".csv"));
                for (String method:Placement.METHODS)
                    execute(trace,cohort+"_"+day,method,101,true,true,false,out);
            }
            // Controlled ablations; use the same old 100 IDs to distinguish data transform and resources.
            Simulation.Stats old=execute(Simulation.read(Paths.get("data/dynamic.csv")),"ablation_v1", "BFD-GA",101,false,false,true,out);
            try (BufferedReader input=Files.newBufferedReader(Paths.get("results/dynamic_summary.csv"))) {
                String line;boolean checked=false;
                while ((line=input.readLine())!=null) if (line.startsWith("BFD-GA,101,")) {
                    double previous=Double.parseDouble(line.split(",")[4]);
                    if (Math.abs(old.totalKwh()-previous)>1e-6) throw new AssertionError("V1 ablation changed baseline energy");
                    checked=true;break;
                }
                if (!checked) throw new IllegalStateException("Historical v1 baseline not found");
            }
            double[][] raw=Simulation.read(Paths.get("data/raw_matrix.csv"));
            execute(raw,"ablation_same100_raw", "BFD-GA",101,false,false,true,out);
            execute(raw,"ablation_same100_raw_types", "BFD-GA",101,true,false,true,out);
            execute(raw,"ablation_same100_periodic", "BFD-GA",101,true,true,true,out);
            execute(main,"ablation_cohort25_uniform", "BFD-GA",101,false,true,true,out);
            execute(main,"ablation_cohort25_overload", "BFD-GA",101,true,false,true,out);
        }
    }
    private static void stable() throws Exception {
        try (PrintWriter out=csv("stable_summary.csv","case,method,seed,resources,controller,vm_count,mean_vm_cpu,mean_physical_host_load,server_kwh,ups_kwh,total_kwh,migrations,active_start,active_end,active_min,active_max,active_mean,above_threshold_host_samples,cpu_error,power_error_w")) {
            double[][] trace=Simulation.read(ROOT.resolve("inputs/cohort25_20110303.csv"));
            for (String method:Placement.METHODS) for (long seed:SEEDS)
                execute(trace,"stable_main",method,seed,true,true,seed==101,out,true);
        }
    }
    private static void statics() throws Exception {
        try (PrintWriter out=csv("static_summary.csv","architecture,target_host_load,actual_host_load,vm_count,method,seed,hosts,server_w,ups_loss_w,total_w,solve_ms,cpu_error,power_error_w")) {
            for (String arch:Experiments.ARCH) for (int level=10;level<=70;level+=10) {
                double[][] trace=Simulation.read(ROOT.resolve("inputs/static_"+level+".csv"));
                double[] mips=DynamicController.vmMips(trace.length,true),d=DynamicController.demand(trace,0,mips);
                double offered=Arrays.stream(d).sum()/100;
                for (String method:Placement.METHODS) for (long seed:SEEDS) {
                    PowerModels.Ups ups=PowerModels.model(arch);
                    Placement.Answer answer=Placement.solve(method,d,100,5,ups,seed,Placement.GENERATIONS,1);
                    Simulation.Stats stats=Simulation.run(trace,answer.host,100,5,ups,method,seed,false,null,
                            new Simulation.Options(mips,false,false));
                    double server=stats.serverKwh*3600000/300,loss=stats.upsKwh*3600000/300;
                    out.printf(Locale.US,"%s,%.2f,%.9f,%d,%s,%d,%d,%.9f,%.9f,%.9f,%.6f,%.12g,%.12g%n",
                            arch,level/100.,offered,trace.length,method,seed,Placement.count(answer.host),server,loss,server+loss,
                            answer.nanos/1e6,stats.cpuError,stats.powerError);
                    out.flush();
                }
                System.out.println("Raw static "+arch+" "+level+"% VM count="+trace.length+" completed");
            }
        }
    }
    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US);Files.createDirectories(ROOT.resolve("results"));
        if (Arrays.asList(args).contains("--resume")) {
            Path summaryPath=ROOT.resolve("results/dynamic_summary.csv");
            for (String line:Files.readAllLines(summaryPath)) if (!line.startsWith("case,") && !line.startsWith("ablation_") && !line.trim().isEmpty()) {
                String[] f=line.split(",");String key=f[0]+","+f[1]+","+f[2];
                Path measured=ROOT.resolve("results").resolve(f[0]+"_"+f[1]+"_"+f[2]+"_times.csv");
                if (f.length!=20 || Files.readAllLines(measured).size()!=289)
                    throw new IllegalStateException("Incomplete resume artifact "+key);
                COMPLETED.add(key);
            }
            System.out.println("Validated resume of "+COMPLETED.size()+" completed heterogeneous raw replays");
        }
        PowerModels.main(new String[0]);Placement.main(new String[0]);DynamicController.main(new String[0]);
        dynamic();stable();statics();System.out.println("PASS corrected experiments: 151 dynamic runs and 700 raw static runs");
    }
}
