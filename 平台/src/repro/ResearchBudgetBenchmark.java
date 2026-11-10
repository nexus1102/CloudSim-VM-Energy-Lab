package repro;
import java.nio.file.*;
import java.io.*;
import java.util.*;

/** Common total-power evaluation; fixed BFD groups remain a different search space. */
public final class ResearchBudgetBenchmark {
    public static void main(String[] args) throws Exception {
        ResearchConfig c=new ResearchConfig(Paths.get(args[0])).with("genetic.objective","total");
        Path output=Paths.get(args[1]);
        if(Files.exists(output))throw new IllegalArgumentException("New budget output required");
        double[][] raw=Simulation.read(Paths.get(c.original.getProperty("trace.path")));
        double[] d=new double[raw.length];
        for(int i=0;i<d.length;i++)d[i]=raw[i][0]*c.settings.vmMips(i)/c.settings.hostMips;
        SupplyPowerModel model=new SupplyPowerModel(c.settings);
        // Warm up all variants equally; warmup is excluded, subsequent solve timers include preprocessing.
        for(String method:ResearchPlacement.METHODS)ResearchPlacement.solve(method,d,c.settings.hosts,c.settings.racks,model,7,2,c.settings.packingCap,false);
        try(PrintWriter w=new PrintWriter(output.toFile(),"UTF-8")) {
            w.println("budget,limit,method,seed,evaluations,generations,solve_ns,total_w,server_w,overrun_ns,host_plan");
            for(long seed:new long[]{101,202,303,404,505}) {
                List<String> methods=new ArrayList<>(Arrays.asList(ResearchPlacement.METHODS));
                Collections.shuffle(methods,new Random(seed));
                for(String method:methods)for(String budget:new String[]{"generations","evaluations","time"}) {
                    if((method.equals("FFD")||method.equals("BFD"))&&!budget.equals("generations"))continue;
                    long eval=budget.equals("evaluations")?4000:Long.MAX_VALUE;
                    long time=budget.equals("time")?100000000L:Long.MAX_VALUE;
                    int gen=budget.equals("generations")?60:1000000;
                    ResearchPlacement.Answer a=ResearchPlacement.solve(method,d,c.settings.hosts,c.settings.racks,model,seed,gen,c.settings.packingCap,false,eval,time);
                    if(a.evaluations>eval)throw new AssertionError("Evaluation budget exceeded");
                    double[] power=model.powers(d,a.host);StringJoiner plan=new StringJoiner(";");for(int h:a.host)plan.add(""+h);
                    w.printf(Locale.US,"%s,%d,%s,%d,%d,%d,%d,%.12f,%.12f,%d,%s%n",budget,budget.equals("generations")?60:budget.equals("evaluations")?4000:100,
                            method,seed,a.evaluations,a.history.length-1,a.nanos,power[2],power[0],budget.equals("time")?Math.max(0,a.nanos-time):0,plan);
                }
            }
            if(w.checkError())throw new IOException("Budget CSV write failed");
        }
    }
}
