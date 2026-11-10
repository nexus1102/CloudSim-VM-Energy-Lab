package repro;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Immutable run directories, public trace snapshots and explicit scenario matrix. */
public final class ResearchExperiments {
    private static final String[] TOPO={"n_plus_1_standby","n_plus_1_shared","two_n"};
    private static final long[] SEEDS={101,202,303};
    private static int dynamicCount,staticCount;
    private static String sha(Path p)throws Exception {MessageDigest d=MessageDigest.getInstance("SHA-256");
        try(InputStream in=Files.newInputStream(p)){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)d.update(b,0,n);}
        StringBuilder s=new StringBuilder();for(byte v:d.digest())s.append(String.format("%02x",v&255));return s.toString();}
    private static String csv(String v){return "\""+v.replace("\"","\"\"")+"\"";}
    private static Path snapshot(Path source,Path root)throws Exception {
        Path target=root.resolve("inputs").resolve(source.getFileName());
        if(!Files.exists(target))Files.copy(source,target);
        if(!sha(source).equals(sha(target)))throw new IllegalStateException("Input filename collision or changed source "+source);
        return target;
    }
    private static PrintWriter writer(Path root,String name,String header)throws Exception {
        PrintWriter w=new PrintWriter(root.resolve(name).toFile(),"UTF-8");w.println(header);return w;
    }
    private static void provenance(Path root)throws Exception {
        try(PrintWriter hashes=writer(root,"provenance.csv","path,sha256,archive_path")) {
            for(String dir:new String[]{"src/repro","lib","build","tools"})try(DirectoryStream<Path> stream=Files.newDirectoryStream(Paths.get(dir))) {
                for(Path p:stream)if(Files.isRegularFile(p)){Path frozen=root.resolve("source_snapshot").resolve(p);Files.createDirectories(frozen.getParent());Files.copy(p,frozen);
                    hashes.println(csv(p.toAbsolutePath().normalize().toString())+","+sha(frozen)+","+csv(root.relativize(frozen).toString()));}
            }
            for(String name:new String[]{"build.ps1","run_research_platform.ps1","runtime.ps1","requirements.txt","requirements-lock.txt"}) {
                Path p=Paths.get(name),frozen=root.resolve("source_snapshot").resolve(p);Files.copy(p,frozen);
                hashes.println(csv(p.toAbsolutePath().normalize().toString())+","+sha(frozen)+","+csv(root.relativize(frozen).toString()));
            }
            if(hashes.checkError())throw new IOException("Provenance snapshot write failed");
        }
    }
    private static void execute(PrintWriter out,Path root,String id,String kind,Path trace,ResearchConfig c,String method,long seed,int[] fixed,boolean detailed)throws Exception {
        double[][] raw=Simulation.read(trace);c=c.with("experiment.seed",""+seed).with("trace.path",trace.toString());
        long nativeBefore=ResearchDestination.nativeCalls;ResearchDatacenter dc=ResearchRun.run(raw,c,method,seed,fixed,root.resolve("cases/"+id),detailed);
        out.printf(Locale.US,"%s,%s,%s,%s,%d,%s,%.12f,%.12f,%.12f,%.12f,%.12f,%d,%d,%d,%.9f,%.9f,%.9f,%.9f,%d,%d%n",id,kind,c.topology,method,seed,csv(trace.toString()),
                dc.hostModelJ/3600000,dc.hardwareJ/3600000,dc.serverJ/3600000,dc.upsJ/3600000,dc.kwh(),dc.starts,dc.finishes,dc.blocked,
                dc.requestedMI,dc.deliveredMI,dc.migrationSeconds,dc.cpuCheckError,raw.length,ResearchDestination.nativeCalls-nativeBefore);
        out.flush();if(out.checkError())throw new IOException("Research summary write failed");
        if(kind.equals("dynamic"))dynamicCount++;if(kind.equals("static"))staticCount++;
        System.out.printf(Locale.US,"research %s %.3fkWh migration=%d%n",id,dc.kwh(),dc.starts);
    }
    private static void benchmark(Path root,ResearchConfig base,Path trace)throws Exception {
        double[][] raw=Simulation.read(trace);
        try(PrintWriter h=writer(root,"histories.csv","n,method,seed,generation,objective_w");
            PrintWriter p=writer(root,"solver_placements.csv","n,method,seed,vm,demand,host,total_w,solve_ms")) {
            for(int n:new int[]{40,150,288}) {
                double[] d=new double[n];for(int i=0;i<n;i++)d[i]=raw[i][0]*base.settings.vmMips(i)/base.settings.hostMips;
                for(String method:new String[]{"GA","GGA","BFD-GA"})for(long seed:SEEDS) {
                    ResearchPlacement.Answer a=ResearchPlacement.solve(method,d,100,5,new SupplyPowerModel(base.settings),seed,60,.9,base.bfdSeed);
                    double total=new SupplyPowerModel(base.settings).powers(d,a.host)[2];
                    for(int j=0;j<a.history.length;j++)h.printf(Locale.US,"%d,%s,%d,%d,%.12f%n",n,method,seed,j,a.history[j]);
                    for(int i=0;i<n;i++)p.printf(Locale.US,"%d,%s,%d,%d,%.17g,%d,%.12f,%.6f%n",n,method,seed,i,d[i],a.host[i],total,a.nanos/1e6);
                }
            }
            if(h.checkError()||p.checkError())throw new IOException("Solver trajectory write failed");
        }
        base.save(root.resolve("benchmark_config.properties"));
    }
    private static void matrix(PrintWriter w,Path root,ResearchConfig base)throws Exception {
        Path trace=snapshot(Paths.get(base.original.getProperty("trace.path")),root);
        for(String topology:TOPO)for(String cap:new String[]{"0.9","1.0"})for(String control:new String[]{"threshold","consolidation"}) {
            ResearchConfig c=base.with("ups.topology",topology).with("packing.cap",cap).with("research.controller",control);
            for(String method:ResearchPlacement.METHODS)for(long seed:SEEDS)
                execute(w,root,topology+"_cap"+cap+"_"+control+"_"+method+"_"+seed,"dynamic",trace,c,method,seed,null,seed==101);
        }
        for(String extension:new String[]{"feasible_init","total_goal","ups_destination","hardware20","standby20"}) {
            ResearchConfig c=extension.equals("feasible_init")?base.with("research.initialization","feasible_packing"):
                    extension.equals("total_goal")?base.with("genetic.objective","total"):
                    extension.equals("ups_destination")?base.with("migration.destination","ups_min_power"):
                    extension.equals("hardware20")?base.with("migration.incremental.w.per.endpoint","20"):base.with("ups.standby.loss.w","20");
            for(String method:ResearchPlacement.METHODS)for(long seed:SEEDS)
                execute(w,root,extension+"_"+method+"_"+seed,"dynamic",trace,c,method,seed,null,seed==101);
        }
        for(String cap:new String[]{"0.9","1.0"})for(String arch:new String[]{"N+1AC","N+1DC","2NAC","2NDC"})for(int level=10;level<=70;level+=10) {
            ResearchConfig c=base.with("research.controller","none").with("packing.cap",cap).with("population","20").with("generations","30")
                    .with("ups.topology",arch.startsWith("2N")?"two_n":"n_plus_1_standby").with("research.static.level",""+level).with("research.architecture",arch);
            if(arch.endsWith("AC"))c=c.with("ups.loss.quadratic",".0376").with("ups.loss.linear",".0069").with("ups.loss.constant",".0319")
                    .with("ups.coefficient.source","Figure 2-5 reconstructed AC fit; named polynomial coefficients");
            Path raw=snapshot(Paths.get("correction/inputs/static_"+level+".csv"),root);
            for(String method:ResearchPlacement.METHODS)for(long seed:SEEDS)
                execute(w,root,"static_cap"+cap+"_"+arch+"_"+level+"_"+method+"_"+seed,"static",raw,c,method,seed,null,false);
        }
        ResearchConfig literal=new ResearchConfig(Paths.get("research_platform/config/paper_validation_literal.properties"));
        execute(w,root,"platform_literal","validation",snapshot(Paths.get(literal.original.getProperty("trace.path")),root),literal,"FIXED",101,SupplyPowerModel.figure14(),true);
        benchmark(root,base,snapshot(Paths.get("correction/inputs/static_30.csv"),root));
        if(dynamicCount!=255||staticCount!=840)throw new AssertionError("Incomplete matrix "+dynamicCount+"/"+staticCount);
    }
    public static void main(String[] args)throws Exception {
        Map<String,String> options=new HashMap<>();
        if(Arrays.asList(args).contains("--help")){System.out.println("--mode single|matrix --config path --output NEW_directory [--method FFD|BFD|GA|GGA|BFD-GA] [--mapping ordered_Host_ID_file]");return;}
        if(args.length%2!=0)throw new IllegalArgumentException("Options require values; use --help");
        for(int i=0;i<args.length;i+=2){if(!Arrays.asList("--mode","--config","--output","--method","--mapping").contains(args[i])||options.put(args[i],args[i+1])!=null)
            throw new IllegalArgumentException("Unknown/duplicate option "+args[i]);}
        String mode=options.getOrDefault("--mode","single");if(!mode.equals("single")&&!mode.equals("matrix"))throw new IllegalArgumentException("Mode must be single or matrix");
        if(!options.containsKey("--output"))throw new IllegalArgumentException("Explicit new --output directory required");
        ResearchConfig config=new ResearchConfig(Paths.get(options.getOrDefault("--config","research_platform/config/default.properties")));
        Path root=Paths.get(options.get("--output")).toAbsolutePath().normalize();
        if(Files.exists(root))throw new IllegalArgumentException("Output already exists; choose a new run directory: "+root);
        if(mode.equals("matrix")&&(options.containsKey("--mapping")||options.containsKey("--method")))throw new IllegalArgumentException("Method/mapping options apply only to single runs");
        Files.createDirectories(root.getParent());Files.createDirectory(root);Files.createDirectories(root.resolve("cases"));Files.createDirectories(root.resolve("inputs"));
        config.save(root.resolve("run_config.properties"));
        provenance(root);
        try(PrintWriter out=writer(root,"summary.csv","prefix,kind,topology,method,seed,raw_path,host_model_kwh,hardware_kwh,server_kwh,ups_kwh,total_kwh,started,finished,blocked,requested_mi,delivered_mi,migration_seconds,cpu_error,vm_count,native_calls")) {
            if(mode.equals("matrix"))matrix(out,root,config);
            else {
                int[] fixed=null;String method=options.getOrDefault("--method","BFD-GA");
                if(options.containsKey("--mapping")){fixed=Arrays.stream(new String(Files.readAllBytes(Paths.get(options.get("--mapping"))),java.nio.charset.StandardCharsets.UTF_8).trim().split("[,\\s]+")).mapToInt(Integer::parseInt).toArray();method="CUSTOM";}
                long seed=Long.parseLong(config.original.getProperty("experiment.seed","101"));
                execute(out,root,"single_"+method,"single",snapshot(Paths.get(config.original.getProperty("trace.path")),root),config,method,seed,fixed,true);
            }
        }
        try(PrintWriter hashes=new PrintWriter(new OutputStreamWriter(new FileOutputStream(root.resolve("provenance.csv").toFile(),true),java.nio.charset.StandardCharsets.UTF_8),true)) {
            try(DirectoryStream<Path> stream=Files.newDirectoryStream(root.resolve("inputs"))){for(Path p:stream)hashes.println(csv(p.toAbsolutePath().normalize().toString())+","+sha(p)+","+csv(root.relativize(p).toString()));}
            if(hashes.checkError())throw new IOException("Input provenance write failed");
        }
        Files.write(root.resolve("completed.txt"),Arrays.asList("PASS: "+mode+"; dynamic="+dynamicCount+"; static="+staticCount));
        System.out.println("PASS completed immutable research run "+root);
    }
}
