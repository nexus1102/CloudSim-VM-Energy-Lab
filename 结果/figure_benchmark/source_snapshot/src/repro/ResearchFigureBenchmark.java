package repro;
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Fixed-budget grid for Figure 2-26; it does not reconstruct an undisclosed author stopping rule. */
public final class ResearchFigureBenchmark {
    private static final int[] SIZES={5,10,12,30,40,80,150,230,288},BUDGETS={3,6,12,28,45,48,59};
    private static final long[] SEEDS={101,202,303};
    private static String sha(Path path)throws Exception {
        MessageDigest digest=MessageDigest.getInstance("SHA-256");
        try(InputStream in=Files.newInputStream(path)){byte[] block=new byte[65536];int n;while((n=in.read(block))>0)digest.update(block,0,n);}
        StringBuilder result=new StringBuilder();for(byte b:digest.digest())result.append(String.format("%02x",b&255));return result.toString();
    }
    private static String quoted(Path p){return "\""+p.toString().replace("\"","\"\"")+"\"";}
    public static void main(String[] args)throws Exception {
        if(args.length!=1)throw new IllegalArgumentException("One completed matrix run path required");
        Path run=Paths.get(args[0]).toAbsolutePath().normalize(),out=run.resolve("report/figure_benchmark");
        if(!Files.isRegularFile(run.resolve("completed.txt")))throw new IllegalArgumentException("Matrix has not completed");
        if(Files.exists(out))throw new IllegalArgumentException("Benchmark output already exists: "+out);
        ResearchConfig config=new ResearchConfig(run.resolve("benchmark_config.properties"));
        Path input=run.resolve("inputs/static_30.csv");double[][] raw=Simulation.read(input);
        if(raw.length<288)throw new IllegalArgumentException("Public static snapshot requires at least 288 VMs");
        Files.createDirectories(out);config.save(out.resolve("config.properties"));Files.copy(input,out.resolve("input.csv"));
        try(PrintWriter manifest=new PrintWriter(out.resolve("provenance.csv").toFile(),"UTF-8")) {
            manifest.println("path,sha256");
            for(String dir:new String[]{"src/repro","lib"})try(DirectoryStream<Path> files=Files.newDirectoryStream(Paths.get(dir))){
                for(Path p:files)if(Files.isRegularFile(p)){Path target=out.resolve("source_snapshot").resolve(p);Files.createDirectories(target.getParent());Files.copy(p,target);
                    manifest.println(quoted(out.relativize(target))+","+sha(target));}
            }
            manifest.println("input.csv,"+sha(out.resolve("input.csv")));manifest.println("config.properties,"+sha(out.resolve("config.properties")));
            if(manifest.checkError())throw new IOException("Benchmark provenance failed");
        }
        SupplyPowerModel model=new SupplyPowerModel(config.settings);
        try(PrintWriter summary=new PrintWriter(out.resolve("summary.csv").toFile(),"UTF-8");
            PrintWriter placements=new PrintWriter(out.resolve("placements.csv").toFile(),"UTF-8");
            PrintWriter history=new PrintWriter(out.resolve("histories.csv").toFile(),"UTF-8")) {
            summary.println("n,budget,method,seed,total_w,objective_w,solve_ms");
            placements.println("n,budget,method,seed,vm,demand,host");history.println("n,budget,method,seed,generation,objective_w");
            int count=0;
            for(int n:SIZES){double[] demand=new double[n];for(int i=0;i<n;i++)demand[i]=raw[i][0]*config.settings.vmMips(i)/config.settings.hostMips;
                int[] base=ResearchPlacement.greedy(demand,100,true,.9);
                summary.printf(Locale.US,"%d,0,BFD,0,%.12f,%.12f,0%n",n,model.powers(demand,base)[2],model.powers(demand,base)[2]);
                for(int i=0;i<n;i++)placements.printf(Locale.US,"%d,0,BFD,0,%d,%.17g,%d%n",n,i,demand[i],base[i]);
                for(int budget:BUDGETS)for(String method:new String[]{"GA","GGA","BFD-GA"})for(long seed:SEEDS){
                    ResearchPlacement.Answer answer=ResearchPlacement.solve(method,demand,100,5,model,seed,budget,.9,config.bfdSeed);
                    summary.printf(Locale.US,"%d,%d,%s,%d,%.12f,%.12f,%.6f%n",n,budget,method,seed,model.powers(demand,answer.host)[2],answer.history[budget],answer.nanos/1e6);
                    for(int i=0;i<n;i++)placements.printf(Locale.US,"%d,%d,%s,%d,%d,%.17g,%d%n",n,budget,method,seed,i,demand[i],answer.host[i]);
                    for(int g=0;g<answer.history.length;g++)history.printf(Locale.US,"%d,%d,%s,%d,%d,%.12f%n",n,budget,method,seed,g,answer.history[g]);
                    count++;
                }
                summary.flush();System.out.println("Figure 2-26 benchmark size="+n+" complete");
            }
            if(count!=567||summary.checkError()||placements.checkError()||history.checkError())throw new IOException("Incomplete benchmark");
        }
        Files.write(out.resolve("completed.txt"),Arrays.asList("567 actual genetic solves + 9 BFD references; independent audit required"));
    }
}
