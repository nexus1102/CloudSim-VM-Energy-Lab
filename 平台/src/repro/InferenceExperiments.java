package repro;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Versioned contrasts; no tuning against desired published rankings. */
public final class InferenceExperiments {
    private static final Path R=Paths.get("paper_alignment/inference/results");
    private static final String[] VARIANTS={"total_original","total_common","server_original","server_common"};
    private static PaperSettings settings(PaperSettings b,String v) {
        return b.with("genetic.objective",v.startsWith("total")?"total":"server_only");
    }
    private static EvidencePlacement.Answer solve(String m,double[] d,PaperSettings s,long seed,int g,boolean common,double cap) {
        return EvidencePlacement.solve(m,d,s.hosts,s.racks,new SupplyPowerModel(s),seed,g,cap,common);
    }
    private static PrintWriter writer(String n,String h)throws Exception {
        PrintWriter w=new PrintWriter(R.resolve(n).toFile(),"UTF-8");w.println(h);return w;
    }
    private static void regression(PaperSettings b)throws Exception {
        double[] d={.6,.44,.43,.21,.13,.11,.08};
        for(String m:PaperPlacement.METHODS)for(long seed:new long[]{101,202,303}) {
            PaperPlacement.Answer old=PaperPlacement.solve(m,d,b.hosts,b.racks,new SupplyPowerModel(b),seed,12,1);
            EvidencePlacement.Answer now=solve(m,d,b,seed,12,false,1);
            if(!Arrays.equals(old.host,now.host)||!Arrays.equals(old.history,now.history))throw new AssertionError("Historical compatibility "+m);
        }
        for(int pop:new int[]{20,30,40,60})for(String m:new String[]{"GA","GGA","BFD-GA"})for(boolean common:new boolean[]{false,true}) {
            EvidencePlacement.Answer a=solve(m,d,b.with("population",""+pop),101,12,common,1);
            for(int j=0;j<a.history.length;j++) {
                if(!Double.isFinite(a.history[j])||(j>0&&a.history[j]>a.history[j-1]+1e-8))throw new AssertionError("Population/elite regression");
            }
            for(double x:EvidencePlacement.loads(d,a.host,b.hosts))if(x>1+1e-8)throw new AssertionError("CPU capacity");
        }
        Files.write(R.resolve("regression.txt"),Arrays.asList("PASS: 15 bitwise historical mapping/history comparisons; 24 population/common-initialization checks (20,30,40,60)."));
    }
    private static void benchmark(PaperSettings b)throws Exception {
        try(PrintWriter h=writer("histories.csv","variant,n,method,seed,generation,objective_w");
            PrintWriter a=writer("benchmark.csv","variant,n,method,seed,objective_w,server_w,ups_w,total_w,hosts,solve_ms");
            PrintWriter p=writer("benchmark_placements.csv","variant,n,method,seed,vm,demand,host")) {
            for(int n:new int[]{5,10,12,30,40,80,150,230,288}) {
                Random rng=new Random(72+n);double[] d=new double[n];for(int i=0;i<n;i++)d[i]=.05+.4*rng.nextDouble();
                for(String v:VARIANTS)for(String m:new String[]{"GA","GGA","BFD-GA"})for(int k=1;k<=5;k++) {
                    PaperSettings s=settings(b,v);long seed=101*k;EvidencePlacement.Answer x=solve(m,d,s,seed,60,v.endsWith("common"),1);
                    double[] pow=new SupplyPowerModel(s).powers(d,x.host);
                    a.printf(Locale.US,"%s,%d,%s,%d,%.12f,%.12f,%.12f,%.12f,%d,%.6f%n",v,n,m,seed,x.history[60],pow[0],pow[1],pow[2],EvidencePlacement.count(x.host),x.nanos/1e6);
                    for(int j=0;j<x.history.length;j++)h.printf(Locale.US,"%s,%d,%s,%d,%d,%.12f%n",v,n,m,seed,j,x.history[j]);
                    for(int i=0;i<n;i++)p.printf(Locale.US,"%s,%d,%s,%d,%d,%.17g,%d%n",v,n,m,seed,i,d[i],x.host[i]);
                }
                System.out.println("inference benchmark n="+n);
            }
            if(h.checkError()||a.checkError()||p.checkError())throw new IOException("Benchmark output failed");
        }
    }
    private static void dynamics(PaperSettings b)throws Exception {
        double[][] raw=Simulation.read(Paths.get("correction/inputs/cohort25_20110303.csv"));
        if(raw.length!=100||raw[0].length!=288)throw new IllegalArgumentException("Expected 100 VM-day traces");
        double[] d=new double[raw.length];for(int i=0;i<d.length;i++)d[i]=raw[i][0]*b.vmMips(i)/b.hostMips;
        double cap=Math.max(b.packingCap,Arrays.stream(d).max().getAsDouble());int count=0;
        try(PrintWriter w=writer("dynamic_summary.csv","prefix,case,variant,method,seed,server_kwh,ups_kwh,total_kwh,started,finished,blocked,requested_mi,delivered_mi,migration_seconds,cpu_error,native_calls")) {
            for(String v:VARIANTS)for(String m:PaperPlacement.METHODS)for(int k=1;k<=5;k++) {
                long seed=101*k;PaperSettings s=settings(b,v).with("controller","framework_underload").with("migration.destination","cloudsim_min_power")
                        .with("online.source","Public native destination; one random overload VM and reconstructed single underload source; not author-complete control");
                int[] initial=solve(m,d,s,seed,s.generations,v.endsWith("common"),cap).host;
                String id=v+"_"+m+"_"+seed;long calls=PublicMigrationDestination.nativeCalls;
                PowerSupplyAwareDataCenter dc=PaperRun.run(raw,s,m,seed,initial,R.resolve(id),k==1);
                calls=PublicMigrationDestination.nativeCalls-calls;
                w.printf(Locale.US,"%s,cohort25_20110303,%s,%s,%d,%.12f,%.12f,%.12f,%d,%d,%d,%.9f,%.9f,%.9f,%.9f,%d%n",id,v,m,seed,
                        dc.serverJ/3600000,dc.upsJ/3600000,dc.kwh(),dc.starts,dc.finishes,dc.blocked,dc.requestedMI,dc.deliveredMI,dc.migrationSeconds,dc.cpuCheckError,calls);
                w.flush();if(w.checkError())throw new IOException("Dynamic output failed");
                System.out.printf(Locale.US,"inference %d/100 %s %.3fkWh%n",++count,id,dc.kwh());
            }
        }
    }
    public static void main(String[] args)throws Exception {
        Files.createDirectories(R);PaperSettings s=new PaperSettings(Paths.get("paper_alignment/config/main.properties"));
        regression(s);benchmark(s);dynamics(s);
        System.out.println("PASS versioned solver regression, 540 anytime benchmarks, 100 controlled dynamic comparisons");
    }
}
