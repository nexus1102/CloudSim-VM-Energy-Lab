package repro;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Native-objective search-space study. The thesis did not publish a success/stop criterion. */
public final class ResearchFigureBenchmarkV10 {
    private static final int[] SIZES={5,10,12,30,40,80,150,230,288},BUDGETS={3,6,12,28,45,48,59,300};
    private static final long[] SEEDS={101,202,303};
    private static String sha(Path p)throws Exception {
        MessageDigest d=MessageDigest.getInstance("SHA-256");
        try(InputStream in=Files.newInputStream(p)){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)d.update(b,0,n);}
        StringBuilder s=new StringBuilder();for(byte v:d.digest())s.append(String.format("%02x",v&255));return s.toString();
    }
    private static PrintWriter writer(Path root,String name,String header)throws Exception {
        PrintWriter w=new PrintWriter(root.resolve(name).toFile(),"UTF-8");w.println(header);return w;
    }
    public static void main(String[] args)throws Exception {
        if(args.length!=2)throw new IllegalArgumentException("Completed matrix and NEW benchmark directory required");
        Path run=Paths.get(args[0]).toAbsolutePath().normalize(),out=Paths.get(args[1]).toAbsolutePath().normalize();
        if(!Files.isRegularFile(run.resolve("completed.txt")))throw new IllegalArgumentException("Matrix incomplete");
        if(Files.exists(out))throw new IllegalArgumentException("Output already exists: "+out);
        ResearchConfig base=new ResearchConfig(run.resolve("benchmark_config.properties"))
            .with("research.genetic.operators","aligned_feasible").with("research.initialization","random_hosts")
            .with("research.rack.operators","aligned_gene")
            .with("genetic.objective","server_only").with("research.bfd.seed","false")
            .with("research.bfd.ga.seed","false").with("research.trace.placements","true");
        double[][] raw=Simulation.read(run.resolve("inputs/static_30.csv"));
        if(raw.length<288)throw new IllegalArgumentException("At least 288 frozen VM demands required");
        Files.createDirectories(out);Files.copy(run.resolve("inputs/static_30.csv"),out.resolve("input.csv"));
        try(PrintWriter hashes=writer(out,"provenance.csv","path,sha256")) {
            for(String dir:new String[]{"src/repro","lib"})try(DirectoryStream<Path> stream=Files.newDirectoryStream(Paths.get(dir))) {
                for(Path p:stream)if(Files.isRegularFile(p)) {
                    Path target=out.resolve("source_snapshot").resolve(p);Files.createDirectories(target.getParent());Files.copy(p,target);
                    hashes.println(out.relativize(target).toString().replace('\\','/')+","+sha(target));
                }
            }
            hashes.println("input.csv,"+sha(out.resolve("input.csv")));
            for(String profile:new String[]{"current128","example4"}) {
                ResearchConfig c=profile.equals("example4")?base.with("vm.ram.mb",""+(base.settings.hostRam/4)):base;
                c.save(out.resolve(profile+".properties"));hashes.println(profile+".properties,"+sha(out.resolve(profile+".properties")));
            }
            if(hashes.checkError())throw new IOException("Provenance write failed");
        }
        try(PrintWriter summary=writer(out,"summary.csv","profile,n,budget,method,seed,hosts,server_w,total_w,objective_w,solve_ms");
            PrintWriter history=writer(out,"histories.csv","profile,n,budget,method,seed,generation,objective_w,host_plan")) {
            int count=0;
            for(String profile:new String[]{"current128","example4"}) {
                ResearchConfig c=new ResearchConfig(out.resolve(profile+".properties"));SupplyPowerModel model=new SupplyPowerModel(c.settings);
                for(int n:SIZES) {
                    double[] demand=new double[n];for(int i=0;i<n;i++)demand[i]=raw[i][0]*c.settings.vmMips(i)/c.settings.hostMips;
                    for(int budget:BUDGETS)for(String method:new String[]{"GA","GGA","BFD-GA"})for(long seed:SEEDS) {
                        ResearchPlacement.Answer a=ResearchPlacement.solve(method,demand,100,5,model,seed,budget,.9,false);
                        double[] power=model.powers(demand,a.host);
                        summary.printf(Locale.US,"%s,%d,%d,%s,%d,%d,%.12f,%.12f,%.12f,%.6f%n",profile,n,budget,method,seed,ResearchPlacement.count(a.host),power[0],power[2],a.history[budget],a.nanos/1e6);
                        for(int g=0;g<a.history.length;g++) {
                            StringJoiner plan=new StringJoiner(";");for(int h:a.mappingHistory[g])plan.add(""+h);
                            history.printf(Locale.US,"%s,%d,%d,%s,%d,%d,%.12f,%s%n",profile,n,budget,method,seed,g,a.history[g],plan);
                        }
                        count++;
                    }
                    summary.flush();history.flush();System.out.println("v10 "+profile+" n="+n+" complete");
                }
            }
            if(count!=1296||summary.checkError()||history.checkError())throw new IOException("Benchmark incomplete");
        }
        Files.write(out.resolve("completed.txt"),Arrays.asList("1296 native-objective solves; independent audit required; same frozen input and two explicitly declared resource assumptions"));
    }
}
