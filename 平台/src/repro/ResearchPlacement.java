package repro;

import java.util.*;
import static repro.PlacementOperators.*;

/** Research solver: explicit random-Host or feasible packing initialization; no author-code equivalence claim. */
public final class ResearchPlacement {
    public static final String[] METHODS = {"FFD", "BFD", "GA", "GGA", "BFD-GA"};
    public static final int POP = 40, GENERATIONS = 60;
    public static final double CROSS = .8, MUTATION = .05;
    public static final class Answer {
        public final int[] host;
        public final double[] history;
        public final long nanos;
        public final long evaluations;
        public final int[][] mappingHistory;
        Answer(int[] host, double[] history, long nanos) {
            this(host,history,nanos,null);
        }
        Answer(int[] host,double[] history,long nanos,int[][] mappings) {
            this(host,history,nanos,mappings,-1);
        }
        Answer(int[] host,double[] history,long nanos,int[][] mappings,long evaluations) {
            this.host=host;this.history=history;this.nanos=nanos;this.mappingHistory=mappings;this.evaluations=evaluations;
        }
    }
    private ResearchPlacement() { }
    public static Integer[] order(double[] d) {
        Integer[] ids = new Integer[d.length];
        for (int i = 0; i < ids.length; i++) ids[i] = i;
        Arrays.sort(ids, (a,b) -> Double.compare(d[b], d[a]));
        return ids;
    }
    public static double[] loads(double[] d, int[] p, int h) {
        if (d.length != p.length) throw new IllegalArgumentException("VM count mismatch");
        double[] u = new double[h];
        for (int i = 0; i < d.length; i++) {
            if (p[i] < 0 || p[i] >= h) throw new IllegalArgumentException("Invalid host for VM " + i);
            u[p[i]] += d[i];
        }
        return u;
    }
    public static int count(int[] p) {
        Set<Integer> s = new HashSet<>(); for (int x : p) s.add(x); return s.size();
    }
    public static int[] greedy(double[] d,int h,boolean best,double cap){return greedy(d,h,best,cap,Integer.MAX_VALUE);}
    private static int[] greedy(double[] d, int h, boolean best, double cap,int limit) {
        int[] p = new int[d.length]; double[] u = new double[h];int[] counts=new int[h];
        for (int i : order(d)) {
            int chosen = -1;
            for (int j = 0; j < h; j++) if (u[j] + d[i] <= cap + PowerModels.EPS && counts[j]<limit) {
                if (chosen < 0 || (best && u[j] > u[chosen])) chosen = j;
                if (!best) break;
            }
            if (chosen < 0) throw new IllegalArgumentException("Insufficient host CPU capacity for VM " + i);
            p[i] = chosen; u[chosen] += d[i];counts[chosen]++;
        }
        return p;
    }
    public static Answer solve(String method, double[] d, int h, int racks, SupplyPowerModel ups,
            long seed, int generations, double cap) {
        return solve(method,d,h,racks,ups,seed,generations,cap,false);
    }
    public static Answer solve(String method, double[] d, int h, int racks, SupplyPowerModel ups,
            long seed, int generations, double cap, boolean commonSeed) {
        return solve(method,d,h,racks,ups,seed,generations,cap,commonSeed,Long.MAX_VALUE,Long.MAX_VALUE);
    }
    /** Budgets stop at full population checkpoints; nanos include BFD and initialization. */
    public static Answer solve(String method,double[] d,int h,int racks,SupplyPowerModel ups,
            long seed,int generations,double cap,boolean commonSeed,long maxEvaluations,long maxNanos) {
        if(maxEvaluations<1||maxNanos<1)throw new IllegalArgumentException("Positive budgets required");
        long start = System.nanoTime(); Random rng = new Random(seed);
        int limit=(int)Math.min(ups.s.hostRam/ups.s.vmRam,Math.min(ups.s.bandwidth/1000,ups.s.storage/1000));
        if (d.length == 0 || h <= 0 || racks <= 0 || h % racks != 0 || generations < 0 || !(cap > 0 && cap <= 1))
            throw new IllegalArgumentException("Invalid placement problem dimensions");
        for (double v : d) if (!Double.isFinite(v) || v < 0 || v > cap + PowerModels.EPS)
            throw new IllegalArgumentException("VM demand outside host capacity: " + v);
        if (method.equals("FFD") || method.equals("BFD")) {
            int[] p = greedy(d, h, method.equals("BFD"), cap,limit);
            return new Answer(p, new double[]{ups.powers(d,p)[2]}, System.nanoTime()-start,null,1);
        }
        if (!Arrays.asList(METHODS).contains(method)) throw new IllegalArgumentException("Unknown method " + method);
        if(maxEvaluations<ups.s.population)throw new IllegalArgumentException("Evaluation budget must cover the initial population");
        generations=(int)Math.min((long)generations,maxEvaluations/ups.s.population-1);
        boolean twoStep = method.equals("BFD-GA"), grouping = method.equals("GGA");
        String operator=ups.s.values.getProperty("research.genetic.operators","legacy");
        if(!operator.equals("legacy")&&!operator.equals("aligned_feasible"))throw new IllegalArgumentException("Unknown genetic operators: "+operator);
        boolean improved=operator.equals("aligned_feasible"),trace=Boolean.parseBoolean(ups.s.values.getProperty("research.trace.placements","false"));
        String rackOperator=ups.s.values.getProperty("research.rack.operators","legacy");
        if(!rackOperator.equals("legacy")&&!rackOperator.equals("aligned_gene"))throw new IllegalArgumentException("Unknown rack operators: "+rackOperator);
        boolean rackAligned=twoStep&&rackOperator.equals("aligned_gene");
        int[] base = greedy(d, h, true, cap,limit);
        int[] groupIds = Arrays.stream(base).distinct().sorted().toArray();
        int len = twoStep ? groupIds.length : d.length;
        int[][] pop = new int[ups.s.population][];
        for (int k = 0; k < ups.s.population; k++) {
            if (twoStep) {
                int[] genes = new int[len]; for (int i = 0; i < len; i++) genes[i] = rng.nextInt(racks);
                pop[k] = repairRacks(genes,h,racks,rng);
            } else if (ups.s.values.getProperty("research.initialization","feasible_packing").equals("random_hosts")) {
                int[] desired=new int[len];for(int i=0;i<len;i++)desired[i]=rng.nextInt(h);
                pop[k]=repair(d,desired,h,cap,limit);
            } else pop[k] = randomPacking(d,h,rng,cap,limit);
        }
        // Include concentrated BFD only for the proposed second step, giving a no-worse baseline.
        if (twoStep&&Boolean.parseBoolean(ups.s.values.getProperty("research.bfd.ga.seed","true")))
            for (int i = 0; i < len; i++) pop[0][i] = groupIds[i] / (h/racks);
        if (commonSeed && !twoStep) pop[0] = base.clone();
        double[] history = new double[generations+1]; int[] champion = null;
        int[][] mappings=trace?new int[generations+1][]:null;
        int lastGeneration=0;
        for (int gen = 0; gen <= generations; gen++) {
            lastGeneration=gen;
            double[] scores = new double[ups.s.population]; int best = 0;
            for (int k = 0; k < ups.s.population; k++) {
                int[] p = twoStep ? racksToHosts(base,groupIds,pop[k],h,racks) : pop[k];
                double score=ups.score(d,p,twoStep||ups.s.totalObjective);
                double[] power = {score,0,score};
                scores[k] = (twoStep || ups.s.totalObjective) ? power[2] : power[0];
                if (scores[k] < scores[best]) best = k;
            }
            if(!Double.isFinite(scores[best])) throw new IllegalArgumentException("No feasible UPS candidate "+method);
            history[gen] = scores[best]; champion = pop[best].clone();
            if(trace)mappings[gen]=twoStep?racksToHosts(base,groupIds,champion,h,racks):champion.clone();
            if (gen == generations || System.nanoTime()-start>=maxNanos) break;
            int[][] next = new int[ups.s.population][]; next[0] = champion;
            for (int k = 1; k < ups.s.population; k++) {
                int[] a = pop[roulette(scores,rng)], b = pop[roulette(scores,rng)]; int[] child = a.clone();
                if(rackAligned)b=align(a,b,racks,1,false); // Equal UPS models: a rack permutation preserves the parent's power.
                else if(improved&&!twoStep)b=align(a,b,h,racks,ups.s.totalObjective);
                if (rng.nextDouble() < ups.s.cross) {
                    if (grouping) child = groupingChild(d,a,b,h,rng,cap,limit);
                    else {
                        int cut = rng.nextInt(len);
                        for (int i = cut; i < len; i++) child[i] = b[i];
                    }
                }
                if (grouping) {
                    if (rng.nextDouble() < ups.s.mutation) child = mutateGroups(d,child,h,rng,cap,limit);
                } else if(rackAligned) {
                    for(int i=0;i<len;i++)if(rng.nextDouble()<ups.s.mutation)child[i]=rng.nextInt(racks);
                } else if(improved) {
                    if(rng.nextDouble()<ups.s.mutation) {
                        if(twoStep)child[rng.nextInt(len)]=rng.nextInt(racks);
                        else mutateFeasible(d,child,h,rng,cap,limit);
                    }
                } else for (int i = 0; i < len; i++) if (rng.nextDouble() < ups.s.mutation)child[i]=rng.nextInt(twoStep?racks:h);
                next[k] = twoStep ? repairRacks(child,h,racks,rng) : repair(d,child,h,cap,limit);
            }
            pop = next;
        }
        int[] result = twoStep ? racksToHosts(base,groupIds,champion,h,racks) : champion;
        ups.powers(d,result);
        return new Answer(result, Arrays.copyOf(history,lastGeneration+1), System.nanoTime()-start,
                mappings==null?null:Arrays.copyOf(mappings,lastGeneration+1),(long)ups.s.population*(lastGeneration+1));
    }
    /** Explicit PEA-FF reconstruction: rank rack marginal supply cost, then first-fit within rack. */
    public static int[] peaFirstFit(double[] d,SupplyPowerModel model,double cap) {
        int[] plan=new int[d.length];double[] u=new double[model.s.hosts];int[] counts=new int[model.s.hosts];int limit=(int)Math.min(model.s.hostRam/model.s.vmRam,Math.min(model.s.bandwidth/1000,model.s.storage/1000));int width=model.s.hosts/model.s.racks;
        for(int i=0;i<d.length;i++) {
            int best=-1;double delta=Double.POSITIVE_INFINITY;
            for(int rack=0;rack<model.s.racks;rack++) {
                int slot=-1;double output=0;
                for(int h=rack*width;h<(rack+1)*width;h++) {
                    if(counts[h]>0)output+=model.host(u[h],true);
                    if(slot<0&&u[h]+d[i]<=cap+1e-8&&counts[h]<limit)slot=h;
                }
                if(slot<0)continue;
                double extra=model.host(u[slot]+d[i],true)-(counts[slot]>0?model.host(u[slot],true):0);
                if(output+extra>model.s.rated+1e-8)continue;
                double cost=extra+model.loss(output+extra)-model.loss(output);
                if(cost<delta-1e-8){delta=cost;best=slot;}
            }
            if(best<0)throw new IllegalArgumentException("PEA-FF capacity at VM "+i);
            plan[i]=best;u[best]+=d[i];counts[best]++;
        }
        return plan;
    }
    public static void main(String[] args) throws Exception {
        if(args.length==2&&args[0].equals("--diagnose")){diagnose(java.nio.file.Paths.get(args[1]));return;}
        SupplyPowerModel model=new SupplyPowerModel(new PaperSettings(java.nio.file.Paths.get("paper_alignment/config/main.properties")));
        double[] d={.5,.3,.1,.6,.3,.5,.4,.4,.1,.2};
        int[] base=greedy(d,100,true,.9);double[] u=Arrays.stream(loads(d,base,100)).filter(x->x>0).toArray();
        if(!Arrays.equals(u,new double[]{.8999999999999999,.9,.9,.7})) {
            double[] expected={.9,.9,.9,.7};for(int i=0;i<4;i++)SupplyPowerModel.close(u[i],expected[i]);
        }
        double[] distinguish={.6,.44,.43,.21,.13,.11,.08};
        if(count(greedy(distinguish,100,false,1))!=3||count(greedy(distinguish,100,true,1))!=2)throw new AssertionError("FFD/BFD semantics");
        for(String method:METHODS){Answer a=solve(method,d,100,5,model,101,20,.9);
            Answer b=solve(method,d,100,5,model,101,20,.9);
            if(!Arrays.equals(a.host,b.host))throw new AssertionError("seed "+method);
            for(double x:loads(d,a.host,100))if(x>.9+1e-8)throw new AssertionError("capacity");
            if(method.equals("BFD-GA"))for(int i=0;i<d.length;i++)for(int j=0;j<d.length;j++)
                if((base[i]==base[j])!=(a.host[i]==a.host[j]))throw new AssertionError("Stage1 group broken");
        }
        double[] zero=new double[300];Answer z=solve("BFD",zero,100,5,model,101,0,1);
        int[] cnt=new int[100];for(int h:z.host)cnt[h]++;for(int c:cnt)if(c>128)throw new AssertionError("Zero CPU VM RAM overflow");
        ResearchConfig config=new ResearchConfig(java.nio.file.Paths.get("research_platform/config/default.properties"));
        int[] aa={1,1,4,4,9,9},bb={8,8,3,3,6,6};
        if(!Arrays.equals(align(aa,bb,100,5,false),aa))throw new AssertionError("Equivalent labels not aligned");
        int[] ra={0,0,1,1,2,2,3,4},rb={4,4,2,2,0,0,1,3};
        if(!Arrays.equals(align(ra,rb,5,1,false),ra))throw new AssertionError("Equivalent rack labels not aligned");
        ResearchConfig fixed=config.with("research.initialization","feasible_packing").with("research.genetic.operators","aligned_feasible").with("research.trace.placements","true");
        double[] small={.10,.08,.05,.04,.02};
        Answer sa=solve("GA",small,100,5,new SupplyPowerModel(fixed.settings),101,3,.9,false);
        if(count(sa.host)!=1)throw new AssertionError("Five VM GA retains avoidable idle Hosts");
        for(int g=0;g<sa.history.length;g++)SupplyPowerModel.close(sa.history[g],new SupplyPowerModel(fixed.settings).powers(small,sa.mappingHistory[g])[0]);
        for(String method:METHODS){Answer a=solve(method,d,100,5,new SupplyPowerModel(fixed.settings),101,12,.9,false);
            Answer b=solve(method,d,100,5,new SupplyPowerModel(fixed.settings),101,12,.9,false);
            if(!Arrays.equals(a.host,b.host))throw new AssertionError("New operator determinism");}
        ResearchConfig rackFixed=fixed.with("research.rack.operators","aligned_gene").with("research.bfd.ga.seed","false");
        Answer rackResult=solve("BFD-GA",d,100,5,new SupplyPowerModel(rackFixed.settings),101,12,.9,false);
        for(int g=0;g<rackResult.history.length;g++) {
            SupplyPowerModel.close(rackResult.history[g],new SupplyPowerModel(rackFixed.settings).powers(d,rackResult.mappingHistory[g])[2]);
            for(int i=0;i<d.length;i++)for(int j=0;j<d.length;j++)if((base[i]==base[j])!=(rackResult.mappingHistory[g][i]==rackResult.mappingHistory[g][j]))throw new AssertionError("Aligned rack operator changed BFD groups");
        }
        for(String init:new String[]{"random_hosts","feasible_packing"})for(int size:new int[]{20,40,60}) {
            PaperSettings rs=config.with("research.initialization",init).with("population",""+size).settings;
            for(String method:METHODS){Answer a=solve(method,d,100,5,new SupplyPowerModel(rs),101,12,.9,false);
                for(double x:loads(d,a.host,100))if(x>.9+1e-8)throw new AssertionError("Research capacity");
                for(int j=1;j<a.history.length;j++)if(a.history[j]>a.history[j-1]+1e-8)throw new AssertionError("Elite trajectory");}
        }
        System.out.println("PASS initialization, aligned-label crossover, feasible chromosome mutation, deterministic real plans, constraints and BFD group preservation");
    }
    private static void diagnose(java.nio.file.Path output)throws Exception {
        if(java.nio.file.Files.exists(output))throw new IllegalArgumentException("Diagnostic output already exists");
        ResearchConfig config=new ResearchConfig(java.nio.file.Paths.get("research_platform/config/default.properties"));
        try(java.io.PrintWriter w=new java.io.PrintWriter(output.toFile(),"UTF-8")) {
            w.println("n,variant,method,initial_hosts,final_hosts,initial_objective_w,final_objective_w,total_w");
            for(int level:new int[]{10,70}) {
                double[][] raw=Simulation.read(java.nio.file.Paths.get("correction/inputs/static_"+level+".csv"));double[] d=new double[raw.length];
                for(int i=0;i<d.length;i++)d[i]=raw[i][0]*config.settings.vmMips(i)/config.settings.hostMips;
                for(String op:new String[]{"legacy","aligned_feasible"})for(String init:new String[]{"random_hosts","feasible_packing"}) {
                    ResearchConfig c=config.with("research.genetic.operators",op).with("research.initialization",init).with("research.trace.placements","true");
                    SupplyPowerModel model=new SupplyPowerModel(c.settings);
                    for(String method:new String[]{"GA","GGA","BFD-GA"}) {
                        Answer a=solve(method,d,100,5,model,101,30,.9,false);
                        w.printf(java.util.Locale.US,"%d,%s_%s,%s,%d,%d,%.12f,%.12f,%.12f%n",d.length,op,init,method,count(a.mappingHistory[0]),count(a.host),a.history[0],a.history[30],model.powers(d,a.host)[2]);
                    }
                }
            }
            if(w.checkError())throw new java.io.IOException("Diagnostic CSV write failed");
        }
    }
}
