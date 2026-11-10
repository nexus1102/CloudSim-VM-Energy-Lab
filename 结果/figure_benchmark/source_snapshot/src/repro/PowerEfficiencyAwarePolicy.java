package repro;
import java.util.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.power.PowerVmAllocationPolicyAbstract;
import org.cloudbus.cloudsim.power.PowerHost;

/** Paper threshold selection; destination and partial-group adaptation are explicit reconstruction. */
public final class PowerEfficiencyAwarePolicy extends PowerVmAllocationPolicyAbstract {
    public final PaperSettings s;public final SupplyPowerModel power;public final String method;
    private int[] initial;private final Map<String,Host> table;
    private final Random selection;private long round=0;public int rejected;
    public PowerEfficiencyAwarePolicy(List<? extends Host> hosts,PaperSettings s,String method,long seed){
        super(hosts);this.s=s;this.method=method;power=new SupplyPowerModel(s);selection=new Random(seed);table=getVmTable();}
    @Override public PowerHost findHostForVm(Vm vm){return initial==null?null:(PowerHost)getHostList().get(initial[vm.getId()]);}
    public void initial(int[] plan){initial=plan.clone();}
    public boolean allocateHostForVm(Vm vm){if(initial==null)throw new IllegalStateException("Initial placement not generated");
        return allocateHostForVm(vm,getHostList().get(initial[vm.getId()]));}
    public boolean allocateHostForVm(Vm vm,Host h){if(!h.vmCreate(vm))return false;table.put(vm.getUid(),h);return true;}
    public void deallocateHostForVm(Vm vm){Host h=table.remove(vm.getUid());if(h!=null)h.vmDestroy(vm);}
    public Host getHost(Vm vm){return table.get(vm.getUid());}
    public Host getHost(int id,int user){return table.get(Vm.getUid(user,id));}
    public List<Map<String,Object>> optimizeAllocation(List<? extends Vm> vms){
        List<Map<String,Object>> result=new ArrayList<>();if(s.controller.equals("none"))return result;
        double[] demand=new double[vms.size()];int[] old=new int[vms.size()];List<Integer> selected=new ArrayList<>();
        for(Vm v:vms){demand[v.getId()]=v.getCurrentRequestedTotalMips()/s.hostMips;old[v.getId()]=v.getHost().getId();}
        for(Host h:getHostList()){
            if(!s.controller.equals("periodic_extension")&&((HostDynamicWorkload)h).getUtilizationOfCpu()<=s.trigger+1e-8)continue;
            List<Integer> candidates=new ArrayList<>();boolean busy=false;
            for(Vm v:h.getVmList()){
                if(v.isInMigration())busy=true;
                if(v.getHost()==h&&!v.isInMigration())candidates.add(v.getId());
            }
            if(busy||candidates.isEmpty())continue;
            if(s.controller.equals("periodic_extension"))selected.addAll(candidates);
            else selected.add(candidates.get(selection.nextInt(candidates.size())));
        }
        if(selected.isEmpty()){if(s.controller.equals("framework_underload"))result.addAll(underload(vms,demand,old,result));return result;}
        int[] next=s.destination.equals("legacy")?destinations(demand,old,selected,s,power,method,1000003L*(++round)):
                PublicMigrationDestination.overload(vms,getHostList(),selected,s);
        for(int i:selected){Vm vm=vms.get(i);Host target=getHostList().get(next[i]);
            if(next[i]==old[i]||demand[i]<=1e-10){rejected++;continue;}
            boolean busy=false;for(Vm x:target.getVmList())if(x.isInMigration())busy=true;
            if(busy||target.getRamProvisioner().getAvailableRam()<vm.getRam()
                    ||target.getBwProvisioner().getAvailableBw()<vm.getBw()||target.getStorage()<vm.getSize()){rejected++;continue;}
            Map<String,Object> move=new HashMap<>();move.put("vm",vm);move.put("host",target);move.put("source",vm.getHost());
            move.put("reason",s.controller.equals("periodic_extension")?"periodic_extension":"over90_random_one");result.add(move);
        }
        if(s.controller.equals("framework_underload"))result.addAll(underload(vms,demand,old,result));
        return result;
    }
    /** Framework-inspired evacuation, not a claim about the author's unpublished underload handler. */
    private List<Map<String,Object>> underload(List<? extends Vm> vms,double[] d,int[] old,List<Map<String,Object>> overload){
        if(!s.destination.equals("legacy"))return PublicMigrationDestination.underload(vms,getHostList(),overload,s);
        Set<Integer> excluded=new HashSet<>();for(Map<String,Object> x:overload){excluded.add(((Host)x.get("source")).getId());excluded.add(((Host)x.get("host")).getId());}
        int source=-1;double minimum=1;
        for(Host h:getHostList()){
            double u=((HostDynamicWorkload)h).getUtilizationOfCpu();boolean busy=false;for(Vm v:h.getVmList())if(v.isInMigration())busy=true;
            if(!busy&&!excluded.contains(h.getId())&&u>0&&u<s.trigger&&u<minimum){source=h.getId();minimum=u;}
        }
        List<Map<String,Object>> moves=new ArrayList<>();if(source<0)return moves;
        List<Integer> ids=new ArrayList<>();for(int i=0;i<old.length;i++)if(old[i]==source)ids.add(i);
        ids.sort((a,b)->Double.compare(d[b],d[a]));int[] next=old.clone();double[] u=PaperPlacement.loads(d,old,s.hosts);
        int[] count=new int[s.hosts];for(int h:old)count[h]++;u[source]=0;count[source]=0;
        for(int i:ids){int target=-1;double best=Double.POSITIVE_INFINITY;
            for(int h=0;h<s.hosts;h++)if(h!=source&&count[h]>0&&!excluded.contains(h)&&u[h]+d[i]<=s.trigger+1e-8&&(count[h]+1)*s.vmRam<=s.hostRam){
                boolean busy=false;for(Vm v:getHostList().get(h).getVmList())if(v.isInMigration())busy=true;if(busy)continue;
                next[i]=h;double cost=method.equals("FFD")?h:method.equals("BFD")?-u[h]:score(d,next,power,true);
                if(cost<best){best=cost;target=h;}
            }
            if(target<0)return Collections.emptyList();next[i]=target;u[target]+=d[i];count[target]++;
            Map<String,Object> move=new HashMap<>();move.put("vm",vms.get(i));move.put("source",getHostList().get(source));
            move.put("host",getHostList().get(target));move.put("reason","framework_underload_reconstruction");moves.add(move);
        }return moves;
    }
    private static double score(double[] d,int[] p,SupplyPowerModel m,boolean total){
        double[] u=PaperPlacement.loads(d,p,m.s.hosts);int[] count=new int[u.length];for(int h:p)count[h]++;
        double[] rack=new double[m.s.racks];double server=0,loss=0;
        for(int h=0;h<u.length;h++){double w=m.host(Math.min(1,u[h]),count[h]>0);server+=w;rack[h/(u.length/rack.length)]+=w;}
        for(double w:rack){if(w>m.s.rated+1e-8)return Double.POSITIVE_INFINITY;loss+=m.loss(w);}
        return server+(total?loss:0);
    }
    private static int[] repair(double[] d,int[] old,List<Integer> moved,int[] desired,PaperSettings s){
        int[] p=old.clone(),counts=new int[s.hosts];double[] u=PaperPlacement.loads(d,old,s.hosts);
        for(int h:old)counts[h]++;for(int i:moved){u[old[i]]-=d[i];counts[old[i]]--;}
        List<Integer> ids=new ArrayList<>(moved);ids.sort((a,b)->Double.compare(d[b],d[a]));
        for(int i:ids){int h=desired[i],best=-1;
            for(int j=0;j<s.hosts;j++)if(j!=old[i]&&u[j]+d[i]<=Math.max(s.trigger,d[i])+1e-8
                    &&(counts[j]+1)*s.vmRam<=s.hostRam&&(best<0||u[j]>u[best]))best=j;
            if(h<0||h>=s.hosts||h==old[i]||u[h]+d[i]>Math.max(s.trigger,d[i])+1e-8||(counts[h]+1)*s.vmRam>s.hostRam)h=best;
            if(h<0)h=old[i];p[i]=h;u[h]+=d[i];counts[h]++;
        }return p;
    }
    public static int[] destinations(double[] d,int[] old,List<Integer> moved,PaperSettings s,
            SupplyPowerModel m,String method,long seed){
        int[] unspecified=old.clone();for(int i:moved)unspecified[i]=-1;
        int[] base=repair(d,old,moved,unspecified,s);
        if(method.equals("FFD")){
            double[] u=PaperPlacement.loads(d,old,s.hosts);for(int i:moved)u[old[i]]-=d[i];int[] p=old.clone();
            List<Integer> ids=new ArrayList<>(moved);ids.sort((a,b)->Double.compare(d[b],d[a]));
            int[] counts=new int[s.hosts];for(int h:old)counts[h]++;for(int i:moved)counts[old[i]]--;
            for(int i:ids){int h=-1;for(int j=0;j<s.hosts;j++)if(j!=old[i]&&u[j]+d[i]<=Math.max(s.trigger,d[i])+1e-8
                    &&(counts[j]+1)*s.vmRam<=s.hostRam){h=j;break;}
                if(h<0)h=old[i];p[i]=h;u[h]+=d[i];counts[h]++;}return p;
        }
        if(method.equals("BFD"))return base;
        Random rng=new Random(seed);int n=s.population;int[][] pop=new int[n][];
        boolean two=method.equals("BFD-GA"),group=method.equals("GGA"),total=two||s.totalObjective;
        Set<Integer> moving=new HashSet<>(moved);int[] fixedCount=new int[s.hosts];for(int i=0;i<old.length;i++)if(!moving.contains(i))fixedCount[old[i]]++;
        for(int k=0;k<n;k++){int[] genes=base.clone();if(k>0)for(int i:moved)genes[i]=rng.nextInt(s.hosts);
            pop[k]=two?groupRepair(d,old,moved,base,genes,fixedCount,s):repair(d,old,moved,genes,s);}
        int[] champion=base;
        for(int gen=0;gen<=s.generations;gen++){
            double[] scores=new double[n];int best=0;for(int k=0;k<n;k++){scores[k]=score(d,pop[k],m,total);if(scores[k]<scores[best])best=k;}
            champion=pop[best].clone();if(gen==s.generations)break;
            int[][] next=new int[n][];next[0]=champion;
            for(int k=1;k<n;k++){int[] a=pop[parent(scores,rng)],b=pop[parent(scores,rng)],child=a.clone();
                if(rng.nextDouble()<s.cross){int selected=moved.get(rng.nextInt(moved.size()));int cut=rng.nextInt(moved.size());
                    for(int z=0;z<moved.size();z++){int i=moved.get(z);if(group?b[i]==b[selected]:z>=cut)child[i]=b[i];}}
                if(group){if(rng.nextDouble()<s.mutation){int selected=moved.get(rng.nextInt(moved.size())),h=rng.nextInt(s.hosts);
                    for(int i:moved)if(a[i]==a[selected])child[i]=h;}}
                else for(int i:moved)if(rng.nextDouble()<s.mutation)child[i]=rng.nextInt(s.hosts);
                next[k]=two?groupRepair(d,old,moved,base,child,fixedCount,s):repair(d,old,moved,child,s);
            }pop=next;
        }
        return champion;
    }
    private static int[] groupRepair(double[] d,int[] old,List<Integer> moved,int[] base,int[] desired,int[] fixed,PaperSettings s){
        int[] p=base.clone();boolean[] used=new boolean[s.hosts];double[] u=new double[s.hosts];
        Set<Integer> moving=new HashSet<>(moved);for(int i=0;i<old.length;i++)if(!moving.contains(i))u[old[i]]+=d[i];
        for(int g:moved.stream().mapToInt(i->base[i]).distinct().toArray()){
            List<Integer> members=new ArrayList<>();for(int i:moved)if(base[i]==g)members.add(i);
            // Groups merged into nonmoving hosts are immovable; only evacuated groups may change rack/slot.
            int target=fixed[g]>0?g:desired[members.get(0)];double load=0;for(int i:members)load+=d[i];
            boolean valid=target>=0&&target<s.hosts&&!used[target]&&fixed[target]==0&&u[target]+load<=s.trigger+1e-8;
            for(int i:members)if(target==old[i])valid=false;
            if(fixed[g]>0||!valid)target=g;
            if(used[target])return base.clone();used[target]=true;u[target]+=load;for(int i:members)p[i]=target;
        }return p;
    }
    private static int parent(double[] scores,Random r){double max=0,total=0;for(double x:scores)if(Double.isFinite(x))max=Math.max(max,x);
        for(double x:scores)if(Double.isFinite(x))total+=max-x+1e-3;double spin=r.nextDouble()*total;
        for(int i=0;i<scores.length;i++)if(Double.isFinite(scores[i])&&(spin-=max-scores[i]+1e-3)<=0)return i;
        throw new IllegalStateException("No finite migration candidate");}
    public static void main(String[] args) throws Exception {
        PaperSettings s=new PaperSettings(java.nio.file.Paths.get("paper_alignment/config/main.properties"));SupplyPowerModel m=new SupplyPowerModel(s);
        double[] d={.6,.5,.2,.1};int[] old={0,0,1,1};
        for(String method:PaperPlacement.METHODS){int[] next=destinations(d,old,Arrays.asList(1),s,m,method,101);
            if(next[0]!=0||next[2]!=1||next[3]!=1||next[1]==0)throw new AssertionError("Unselected VM moved "+method);}
        System.out.println("PASS restricted migration: unselected VMs remain fixed for five methods");
    }
}
