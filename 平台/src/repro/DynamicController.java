package repro;

import java.util.*;
import java.nio.file.*;

/** Common dynamic controller: current-snapshot optimization, not trace smoothing. */
public final class DynamicController {
    private DynamicController() { }
    public static double capacity(double[] physicalDemand) {
        double capacity=.9;
        for (double d:physicalDemand) {
            if (!Double.isFinite(d) || d<0 || d>1+PowerModels.EPS)
                throw new IllegalArgumentException("VM exceeds physical PE capacity: "+d);
            capacity=Math.max(capacity,d);
        }
        // 90% is a migration trigger, not a physical limit. A single 100% VM remains feasible.
        return Math.min(capacity,1);
    }
    public static int[] replan(String method,double[] demand,int[] previous,int hosts,int racks,
            PowerModels.Ups ups,long seed) {
        return replan(method,demand,previous,hosts,racks,ups,seed,false);
    }
    public static int[] replan(String method,double[] demand,int[] previous,int hosts,int racks,
            PowerModels.Ups ups,long seed,boolean stable) {
        Placement.Answer answer=Placement.solve(method,demand,hosts,racks,ups,seed,
                Placement.GENERATIONS,capacity(demand));
        int[] planned=stable?matchRackNames(answer.host,previous,hosts,racks):answer.host;
        int[] result=stabilize(planned,previous,hosts,racks);
        if (stable) {
            double cap=capacity(demand);boolean feasible=true;
            for (double load:Placement.loads(demand,previous,hosts)) if (load>cap+PowerModels.EPS) feasible=false;
            if (feasible) {
                int metric=method.equals("BFD-GA")?2:0;
                if (PowerModels.powers(demand,previous,hosts,racks,ups)[metric]
                        <=PowerModels.powers(demand,result,hosts,racks,ups)[metric]+1e-6) return previous.clone();
            }
        }
        return result;
    }
    private static int[] matchRackNames(int[] planned,int[] previous,int hosts,int racks) {
        if (racks>6) return planned; // bounded permutation search; current case has five identical UPS racks.
        int[][] overlap=new int[racks][racks];int width=hosts/racks;
        for (int i=0;i<planned.length;i++) overlap[planned[i]/width][previous[i]/width]++;
        int[] map=new int[racks],best=new int[racks];int[] score={-1};
        rackPermutation(0,map,new boolean[racks],overlap,best,score);
        int[] mapped=planned.clone();
        for (int i=0;i<mapped.length;i++) mapped[i]=best[planned[i]/width]*width+planned[i]%width;
        return mapped;
    }
    private static void rackPermutation(int depth,int[] map,boolean[] used,int[][] overlap,int[] best,int[] bestScore) {
        if (depth==map.length) {
            int score=0;for (int i=0;i<map.length;i++) score+=overlap[i][map[i]];
            if (score>bestScore[0]) { bestScore[0]=score;System.arraycopy(map,0,best,0,map.length); }
            return;
        }
        for (int r=0;r<map.length;r++) if (!used[r]) {
            used[r]=true;map[depth]=r;rackPermutation(depth+1,map,used,overlap,best,bestScore);used[r]=false;
        }
    }
    public static int[] stabilize(int[] planned,int[] previous,int hosts,int racks) {
        if (planned.length!=previous.length || hosts<=0 || racks<=0 || hosts%racks!=0)
            throw new IllegalArgumentException("Invalid identity-preservation dimensions");
        int width=hosts/racks; int[] mapping=new int[hosts]; Arrays.fill(mapping,-1);
        for (int rack=0;rack<racks;rack++) {
            int start=rack*width;
            int[][] overlap=new int[width][width]; boolean[] active=new boolean[width];
            for (int i=0;i<planned.length;i++) {
                if (planned[i]<0 || planned[i]>=hosts || previous[i]<0 || previous[i]>=hosts)
                    throw new IllegalArgumentException("Host ID outside physical topology");
                if (planned[i]/width==rack) {
                    active[planned[i]-start]=true;
                    if (previous[i]/width==rack) overlap[planned[i]-start][previous[i]-start]++;
                }
            }
            boolean[] occupied=new boolean[width],assigned=new boolean[width];
            // Stable matching heuristic within each rack. Permutations preserve rack power and fitness.
            for (int k=0;k<width;k++) {
                int group=-1,slot=-1,best=-1;
                for (int g=0;g<width;g++) if (active[g] && !assigned[g])
                    for (int s=0;s<width;s++) if (!occupied[s] && overlap[g][s]>best) {
                        group=g;slot=s;best=overlap[g][s];
                    }
                if (group<0) break;
                mapping[start+group]=start+slot;assigned[group]=true;occupied[slot]=true;
            }
        }
        int[] result=new int[planned.length];
        for (int i=0;i<result.length;i++) result[i]=mapping[planned[i]];
        return result;
    }
    public static double[] vmMips(int count,boolean heterogeneous) {
        double[] types={2500,2000,1000,500},mips=new double[count];
        for (int i=0;i<count;i++) mips[i]=heterogeneous?types[i%types.length]:Simulation.MIPS;
        return mips;
    }
    public static double[] demand(double[][] trace,int sample,double[] vmMips) {
        if (trace.length!=vmMips.length) throw new IllegalArgumentException("VM MIPS count mismatch");
        boolean uniform=Arrays.stream(vmMips).allMatch(m->m==Simulation.MIPS);
        double[] d=new double[trace.length];
        for (int i=0;i<d.length;i++) d[i]=uniform?trace[i][sample]:trace[i][sample]*vmMips[i]/Simulation.MIPS;
        return d;
    }
    public static void main(String[] args) throws Exception {
        if (capacity(new double[]{1})!=1) throw new AssertionError("Single full-CPU VM incorrectly rejected");
        int[] a={0,0,1,5},b={1,1,0,7}; double[] d={.2,.3,.4,.1};
        int[] c=stabilize(a,b,10,2);
        double[] before=PowerModels.powers(d,a,10,2,new PowerModels.Ups(2000,.0241,.0353,.0617,1));
        double[] after=PowerModels.powers(d,c,10,2,new PowerModels.Ups(2000,.0241,.0353,.0617,1));
        for (int i=0;i<3;i++) PowerModels.close(before[i],after[i]);
        int[] retained=replan("BFD",new double[]{.6,.6},new int[]{0,5},10,2,
                new PowerModels.Ups(2000,.0241,.0353,.0617,1),202,true);
        if (!Arrays.equals(retained,new int[]{0,5})) throw new AssertionError("Zero-benefit stable controller migrated VMs");
        double[][] t={{.8,.1,.05},{.6,.2,.05},{.5,.1,.05},{.5,.1,.05}};
        double[] mips={2500,2000,1000,500};double[] first=demand(t,0,mips);
        int[] initial=Placement.greedy(first,10,true,capacity(first));
        Files.createDirectories(Paths.get("correction/results"));
        Simulation.Options options=new Simulation.Options(mips,true,true);
        Simulation.Stats stats=Simulation.run(t,initial,10,2,PowerModels.model("N+1DC"),"BFD-GA",101,true,
                Paths.get("correction/results/controller_smoke"),options);
        if (stats.cpuError>1e-8 || stats.activeEnd>stats.activeStart)
            throw new AssertionError("Periodic consolidation or physical MIPS verification failed");
        Simulation.run(new double[][]{{1,1}},new int[]{0},10,2,PowerModels.model("N+1DC"),"BFD",101,true,null,
                new Simulation.Options(new double[]{2500},true,false));
        Simulation.run(new double[][]{{1,1}},new int[]{0},10,2,PowerModels.model("N+1DC"),"BFD",101,true,null,
                new Simulation.Options(new double[]{2500},false,false));
        System.out.println("PASS raw100% VM, heterogeneous MIPS, rack-invariant mapping, consolidation and 300-second clock");
    }
}
