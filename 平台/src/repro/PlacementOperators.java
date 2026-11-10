package repro;

import java.util.*;
import static repro.ResearchPlacement.order;
import static repro.ResearchPlacement.loads;

/** Internal chromosome operations, shared by the existing solver variants. */
final class PlacementOperators {
    private PlacementOperators() { }
    static int[] repair(double[] d, int[] desired, int h, double cap,int limit) {
        int[] p = new int[d.length]; double[] u = new double[h];int[] counts=new int[h];
        for (int i : order(d)) {
            int t = desired[i];
            if (t < 0 || t >= h || u[t] + d[i] > cap + PowerModels.EPS || counts[t]>=limit) {
                t = -1;
                for (int j = 0; j < h; j++) if (u[j] + d[i] <= cap + PowerModels.EPS && counts[j]<limit
                        && (t < 0 || u[j] > u[t])) t = j;
            }
            if (t < 0) throw new IllegalArgumentException("Chromosome cannot be repaired");
            p[i] = t; u[t] += d[i];counts[t]++;
        }
        return p;
    }
    static int[] randomPacking(double[] d, int h, Random rng, double cap,int limit) {
        List<Integer> ids = new ArrayList<>(); for (int i = 0; i < d.length; i++) ids.add(i);
        Collections.shuffle(ids, rng);
        int[] p = new int[d.length]; double[] u = new double[h];int[] counts=new int[h]; int used = 0;
        for (int i : ids) {
            List<Integer> candidates = new ArrayList<>();
            for (int j = 0; j < used; j++) if (u[j] + d[i] <= cap + PowerModels.EPS && counts[j]<limit) candidates.add(j);
            int t = candidates.isEmpty() ? used++ : candidates.get(rng.nextInt(candidates.size()));
            if (t >= h) throw new IllegalArgumentException("Random packing exceeds host count");
            p[i] = t; u[t] += d[i];counts[t]++;
        }
        List<Integer> physical = new ArrayList<>(); for (int j = 0; j < h; j++) physical.add(j);
        Collections.shuffle(physical, rng);
        for (int i = 0; i < p.length; i++) p[i] = physical.get(p[i]);
        return p;
    }
    static int roulette(double[] score, Random rng) {
        double max=0,total=0;for(double s:score)if(Double.isFinite(s))max=Math.max(max,s);
        for(double s:score)if(Double.isFinite(s))total+=max-s+1e-3;
        double spin=rng.nextDouble()*total;
        for(int i=0;i<score.length;i++)if(Double.isFinite(score[i])&&(spin-=max-score[i]+1e-3)<=0)return i;
        throw new IllegalStateException("No finite genetic parent");
    }
    static int[] groupingChild(double[] d, int[] a, int[] b, int h, Random r, double cap,int limit) {
        int[] groups=Arrays.stream(b).distinct().toArray();
        int selected = groups[r.nextInt(groups.length)];
        Set<Integer> conflicting = new HashSet<>();
        for (int i = 0; i < d.length; i++) if (b[i] == selected) conflicting.add(a[i]);
        int[] child = a.clone(); double[] u = new double[h];
        for (int i = 0; i < d.length; i++) {
            if (conflicting.contains(a[i])) child[i] = -1;
            else u[child[i]] += d[i];
        }
        boolean[] occupied=new boolean[h];for(int x:child)if(x>=0)occupied[x]=true;
        int slot=-1; for(int j=0;j<h;j++) if(!occupied[j]){slot=j;break;}
        if(slot<0) throw new IllegalArgumentException("No free group slot");
        for (int i = 0; i < d.length; i++) if (b[i] == selected) {
            child[i] = slot; u[slot] += d[i];
        }
        insertMissing(d, child, u, cap,limit);
        return child;
    }
    static void insertMissing(double[] d, int[] child, double[] u, double cap,int limit) {
        int[] counts=new int[u.length];for(int x:child)if(x>=0)counts[x]++;
        for (int i : order(d)) if (child[i] < 0) {
            int t = -1;
            for (int j = 0; j < u.length; j++) if (u[j] + d[i] <= cap + PowerModels.EPS && counts[j]<limit
                    && (t < 0 || u[j] > u[t])) t = j;
            if (t < 0) throw new IllegalArgumentException("GGA reinsertion failed");
            child[i] = t; u[t] += d[i];counts[t]++;
        }
    }
    static int[] mutateGroups(double[] d, int[] child, int h, Random rng, double cap,int limit) {
        int[] groups=Arrays.stream(child).distinct().toArray();
        int group = groups[rng.nextInt(groups.length)];
        double[] u = new double[h];
        for (int i = 0; i < child.length; i++) {
            if (child[i] == group) child[i] = -1; else u[child[i]] += d[i];
        }
        insertMissing(d, child, u, cap,limit); return child;
    }
    static int[] racksToHosts(int[] base, int[] groupIds, int[] genes, int h, int racks) {
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
    static int[] repairRacks(int[] genes, int h, int racks, Random rng) {
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
    /** Align equivalent Host labels before crossover; total-power parents preserve rack membership. */
    static int[] align(int[] a,int[] b,int hosts,int racks,boolean keepRack) {
        int[][] overlap=new int[hosts][hosts];boolean[] used=new boolean[hosts];int[] map=new int[hosts];Arrays.fill(map,-1);
        for(int i=0;i<a.length;i++)overlap[b[i]][a[i]]++;
        List<int[]> pairs=new ArrayList<>();int width=hosts/racks;
        for(int x=0;x<hosts;x++)for(int y=0;y<hosts;y++)if(overlap[x][y]>0&&(!keepRack||x/width==y/width))pairs.add(new int[]{x,y,overlap[x][y]});
        pairs.sort((x,y)->{int c=Integer.compare(y[2],x[2]);if(c==0)c=Integer.compare(x[0],y[0]);return c==0?Integer.compare(x[1],y[1]):c;});
        for(int[] p:pairs)if(map[p[0]]<0&&!used[p[1]]){map[p[0]]=p[1];used[p[1]]=true;}
        for(int x=0;x<hosts;x++)if(map[x]<0) {
            int start=keepRack?x/width*width:0,end=keepRack?start+width:hosts;
            if(!used[x]){map[x]=x;used[x]=true;}
            else for(int y=start;y<end;y++)if(!used[y]){map[x]=y;used[y]=true;break;}
            if(map[x]<0)throw new IllegalStateException("Host label alignment has no bijection");
        }
        int[] result=b.clone();for(int i=0;i<result.length;i++)result[i]=map[b[i]];return result;
    }
    /** One feasible move per chromosome mutation event; never randomly opens an idle Host. */
    static void mutateFeasible(double[] demand,int[] plan,int hosts,Random rng,double cap,int limit) {
        double[] load=loads(demand,plan,hosts);int[] count=new int[hosts];for(int h:plan)count[h]++;
        int vm=rng.nextInt(plan.length),source=plan[vm];List<Integer> choices=new ArrayList<>();
        for(int h=0;h<hosts;h++)if(h!=source&&count[h]>0&&count[h]<limit&&load[h]+demand[vm]<=cap+PowerModels.EPS)choices.add(h);
        if(!choices.isEmpty())plan[vm]=choices.get(rng.nextInt(choices.size()));
    }
}
