package repro;

import java.util.*;

/** Five explicitly defined placement methods; no modifications to CloudSim. */
public final class Placement {
    public static final String[] METHODS = {"FFD", "BFD", "GA", "GGA", "BFD-GA"};
    public static final int POP = 40, GENERATIONS = 60;
    public static final double CROSS = .8, MUTATION = .05;
    public static final class Answer {
        public final int[] host;
        public final double[] history;
        public final long nanos;
        Answer(int[] host, double[] history, long nanos) {
            this.host = host; this.history = history; this.nanos = nanos;
        }
    }
    private Placement() { }
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
    public static int[] greedy(double[] d, int h, boolean best, double cap) {
        int[] p = new int[d.length]; double[] u = new double[h];
        for (int i : order(d)) {
            int chosen = -1;
            for (int j = 0; j < h; j++) if (u[j] + d[i] <= cap + PowerModels.EPS) {
                if (chosen < 0 || (best && u[j] > u[chosen])) chosen = j;
                if (!best) break;
            }
            if (chosen < 0) throw new IllegalArgumentException("Insufficient host CPU capacity for VM " + i);
            p[i] = chosen; u[chosen] += d[i];
        }
        return p;
    }
    private static int[] repair(double[] d, int[] desired, int h, double cap) {
        int[] p = new int[d.length]; double[] u = new double[h];
        for (int i : order(d)) {
            int t = desired[i];
            if (t < 0 || t >= h || u[t] + d[i] > cap + PowerModels.EPS) {
                t = -1;
                for (int j = 0; j < h; j++) if (u[j] + d[i] <= cap + PowerModels.EPS
                        && (t < 0 || u[j] > u[t])) t = j;
            }
            if (t < 0) throw new IllegalArgumentException("Chromosome cannot be repaired");
            p[i] = t; u[t] += d[i];
        }
        return p;
    }
    private static int[] randomPacking(double[] d, int h, Random rng, double cap) {
        List<Integer> ids = new ArrayList<>(); for (int i = 0; i < d.length; i++) ids.add(i);
        Collections.shuffle(ids, rng);
        int[] p = new int[d.length]; double[] u = new double[h]; int used = 0;
        for (int i : ids) {
            List<Integer> candidates = new ArrayList<>();
            for (int j = 0; j < used; j++) if (u[j] + d[i] <= cap + PowerModels.EPS) candidates.add(j);
            int t = candidates.isEmpty() ? used++ : candidates.get(rng.nextInt(candidates.size()));
            if (t >= h) throw new IllegalArgumentException("Random packing exceeds host count");
            p[i] = t; u[t] += d[i];
        }
        List<Integer> physical = new ArrayList<>(); for (int j = 0; j < h; j++) physical.add(j);
        Collections.shuffle(physical, rng);
        for (int i = 0; i < p.length; i++) p[i] = physical.get(p[i]);
        return p;
    }
    private static int roulette(double[] score, Random rng) {
        double max = Arrays.stream(score).max().getAsDouble(), total = 0;
        for (double v : score) total += max - v + 1e-3;
        double x = rng.nextDouble() * total;
        for (int i = 0; i < score.length; i++) if ((x -= max - score[i] + 1e-3) <= 0) return i;
        return score.length - 1;
    }
    private static int[] groupingChild(double[] d, int[] a, int[] b, int h, Random r, double cap) {
        int selected = b[r.nextInt(b.length)];
        Set<Integer> conflicting = new HashSet<>();
        for (int i = 0; i < d.length; i++) if (b[i] == selected) conflicting.add(a[i]);
        int[] child = a.clone(); double[] u = new double[h];
        for (int i = 0; i < d.length; i++) {
            if (conflicting.contains(a[i]) || a[i] == selected) child[i] = -1;
            else u[child[i]] += d[i];
        }
        for (int i = 0; i < d.length; i++) if (b[i] == selected) {
            child[i] = selected; u[selected] += d[i];
        }
        insertMissing(d, child, u, cap);
        return child;
    }
    private static void insertMissing(double[] d, int[] child, double[] u, double cap) {
        for (int i : order(d)) if (child[i] < 0) {
            int t = -1;
            for (int j = 0; j < u.length; j++) if (u[j] + d[i] <= cap + PowerModels.EPS
                    && (t < 0 || u[j] > u[t])) t = j;
            if (t < 0) throw new IllegalArgumentException("GGA reinsertion failed");
            child[i] = t; u[t] += d[i];
        }
    }
    private static int[] mutateGroups(double[] d, int[] child, int h, Random rng, double cap) {
        int group = child[rng.nextInt(child.length)];
        double[] u = new double[h];
        for (int i = 0; i < child.length; i++) {
            if (child[i] == group) child[i] = -1; else u[child[i]] += d[i];
        }
        insertMissing(d, child, u, cap); return child;
    }
    private static int[] racksToHosts(int[] base, int[] groupIds, int[] genes, int h, int racks) {
        int[] within = new int[racks], map = new int[h]; Arrays.fill(map, -1);
        for (int i = 0; i < groupIds.length; i++) {
            int rack = genes[i];
            if (rack < 0 || rack >= racks || within[rack] >= h / racks)
                throw new IllegalArgumentException("Rack chromosome capacity violated");
            map[groupIds[i]] = rack * (h / racks) + within[rack]++;
        }
        int[] p = new int[base.length]; for (int i = 0; i < p.length; i++) p[i] = map[base[i]];
        return p;
    }
    private static int[] repairRacks(int[] genes, int h, int racks, Random rng) {
        int[] use = new int[racks];
        for (int i = 0; i < genes.length; i++) {
            int rack = genes[i];
            if (rack < 0 || rack >= racks || use[rack] >= h / racks) {
                List<Integer> available = new ArrayList<>();
                for (int j = 0; j < racks; j++) if (use[j] < h / racks) available.add(j);
                if (available.isEmpty()) throw new IllegalArgumentException("Too many server groups");
                rack = available.get(rng.nextInt(available.size())); genes[i] = rack;
            }
            use[rack]++;
        }
        return genes;
    }
    public static Answer solve(String method, double[] d, int h, int racks, PowerModels.Ups ups,
            long seed, int generations, double cap) {
        long start = System.nanoTime(); Random rng = new Random(seed);
        if (d.length == 0 || h <= 0 || racks <= 0 || h % racks != 0 || generations < 0 || !(cap > 0 && cap <= 1))
            throw new IllegalArgumentException("Invalid placement problem dimensions");
        for (double v : d) if (!Double.isFinite(v) || v < 0 || v > cap + PowerModels.EPS)
            throw new IllegalArgumentException("VM demand outside host capacity: " + v);
        if (method.equals("FFD") || method.equals("BFD")) {
            int[] p = greedy(d, h, method.equals("BFD"), cap);
            return new Answer(p, new double[]{PowerModels.powers(d,p,h,racks,ups)[2]}, System.nanoTime()-start);
        }
        if (!Arrays.asList(METHODS).contains(method)) throw new IllegalArgumentException("Unknown method " + method);
        boolean twoStep = method.equals("BFD-GA"), grouping = method.equals("GGA");
        int[] base = greedy(d, h, true, cap);
        int[] groupIds = Arrays.stream(base).distinct().sorted().toArray();
        int len = twoStep ? groupIds.length : d.length;
        int[][] pop = new int[POP][];
        for (int k = 0; k < POP; k++) {
            if (twoStep) {
                int[] genes = new int[len]; for (int i = 0; i < len; i++) genes[i] = rng.nextInt(racks);
                pop[k] = repairRacks(genes,h,racks,rng);
            } else pop[k] = randomPacking(d,h,rng,cap);
        }
        // Include concentrated BFD only for the proposed second step, giving a no-worse baseline.
        if (twoStep) for (int i = 0; i < len; i++) pop[0][i] = groupIds[i] / (h/racks);
        double[] history = new double[generations+1]; int[] champion = null;
        for (int gen = 0; gen <= generations; gen++) {
            double[] scores = new double[POP]; int best = 0;
            for (int k = 0; k < POP; k++) {
                int[] p = twoStep ? racksToHosts(base,groupIds,pop[k],h,racks) : pop[k];
                double[] power = PowerModels.powers(d,p,h,racks,ups);
                scores[k] = twoStep ? power[2] : power[0];
                if (scores[k] < scores[best]) best = k;
            }
            history[gen] = scores[best]; champion = pop[best].clone();
            if (gen == generations) break;
            int[][] next = new int[POP][]; next[0] = champion;
            for (int k = 1; k < POP; k++) {
                int[] a = pop[roulette(scores,rng)], b = pop[roulette(scores,rng)]; int[] child = a.clone();
                if (rng.nextDouble() < CROSS) {
                    if (grouping) child = groupingChild(d,a,b,h,rng,cap);
                    else {
                        int cut = rng.nextInt(len);
                        for (int i = cut; i < len; i++) child[i] = b[i];
                    }
                }
                if (grouping) {
                    if (rng.nextDouble() < MUTATION) child = mutateGroups(d,child,h,rng,cap);
                } else for (int i = 0; i < len; i++) if (rng.nextDouble() < MUTATION)
                    child[i] = rng.nextInt(twoStep ? racks : h);
                next[k] = twoStep ? repairRacks(child,h,racks,rng) : repair(d,child,h,cap);
            }
            pop = next;
        }
        int[] result = twoStep ? racksToHosts(base,groupIds,champion,h,racks) : champion;
        PowerModels.powers(d,result,h,racks,ups);
        return new Answer(result, history, System.nanoTime()-start);
    }
    public static void main(String[] args) {
        double[] d = {.5,.3,.1,.6,.3,.5,.4,.4,.1,.2};
        PowerModels.Ups ups = new PowerModels.Ups(3500,.0376,.0069,.0319,1);
        for (String m : METHODS) {
            Answer a = solve(m,d,20,2,ups,101,20,1);
            Answer b = solve(m,d,20,2,ups,101,20,1);
            if (!Arrays.equals(a.host,b.host)) throw new AssertionError("Non-reproducible seed " + m);
            if (count(a.host) < 4) throw new AssertionError("Packing below CPU lower bound");
            for (double u : loads(d,a.host,20)) if (u > 1 + PowerModels.EPS) throw new AssertionError("CPU overload");
            for (int i = 1; i < a.history.length; i++) if (a.history[i] > a.history[i-1]+1e-7)
                throw new AssertionError("Elitism lost best solution");
            System.out.println("PASS " + m + " hosts=" + count(a.host));
        }
        int[] p = greedy(d,20,true,1);
        Answer a = solve("BFD-GA",d,20,2,ups,101,20,1);
        PowerModels.close(PowerModels.powers(d,p,20,2,ups)[0],PowerModels.powers(d,a.host,20,2,ups)[0]);
        if (PowerModels.powers(d,a.host,20,2,ups)[2] > PowerModels.powers(d,p,20,2,ups)[2]+1e-7)
            throw new AssertionError("Two-step inferior to retained BFD candidate");
    }
}
