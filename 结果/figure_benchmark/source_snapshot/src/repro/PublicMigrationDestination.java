package repro;
import java.util.*;
import java.nio.file.Paths;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.power.*;
import org.cloudbus.cloudsim.provisioners.*;

/** Executes CloudSim's original minimum-incremental-host-power finder on detached resource views.
 * Reference: Beloglazov/Buyya, CCPE 2012, doi:10.1002/cpe.1867; GPL CloudSim dependency.
 * UPS scoring is our explicit extension, never attributed to Ye's unpublished online implementation.
 */
public final class PublicMigrationDestination extends PowerVmAllocationPolicyMigrationStaticThreshold {
    private final PaperSettings s;private final SupplyPowerModel power;private final List<View> views;
    public static long nativeCalls;
    private static final class View extends PowerHost {
        final PaperSettings settings;double cpu,requested;int entries,freeRam;long freeBw,freeStorage;
        View(Host h,PaperSettings s){this(h,s,Arrays.asList(new Pe(0,new PeProvisionerSimple(s.hostMips))));}
        private View(Host h,PaperSettings s,List<Pe> pes){
            super(h.getId(),new RamProvisionerSimple(s.hostRam),new BwProvisionerSimple(s.bandwidth),s.storage,pes,
                    new VmSchedulerTimeShared(pes),new SupplyPowerModel(s));settings=s;
            cpu=((HostDynamicWorkload)h).getUtilizationOfCpu();entries=h.getVmList().size();
            freeRam=h.getRamProvisioner().getAvailableRam();freeBw=h.getBwProvisioner().getAvailableBw();freeStorage=h.getStorage();
            for(Vm v:h.getVmList())requested+=v.getCurrentRequestedTotalMips()/s.hostMips;
        }
        @Override public boolean isSuitableForVm(Vm vm){return vm.getNumberOfPes()==1&&vm.getMips()<=settings.hostMips
                &&cpu+vm.getCurrentRequestedTotalMips()/settings.hostMips<=1+1e-8
                &&freeRam>=vm.getRam()&&freeBw>=vm.getBw()&&freeStorage>=vm.getSize();}
        @Override public double getPower(){return entries==0?0:settings.idle+(settings.max-settings.idle)*Math.min(1,cpu);}
        void reserve(Vm vm,int sign){requested+=sign*vm.getCurrentRequestedTotalMips()/settings.hostMips;
            entries+=sign;freeRam-=sign*vm.getRam();freeBw-=sign*vm.getBw();freeStorage-=sign*vm.getSize();
            cpu=Math.min(1,Math.max(0,requested));}
    }
    private static List<View> snapshot(List<? extends Host> hosts,PaperSettings s){
        if(hosts.size()!=s.hosts)throw new IllegalArgumentException("Destination snapshot host count differs from configuration");
        List<View> list=new ArrayList<>();for(Host h:hosts){if(h.getId()!=list.size()||h.getNumberOfPes()!=1||Math.abs(h.getTotalMips()-s.hostMips)>1e-7)
            throw new IllegalArgumentException("Destination adapter requires contiguous homogeneous single-PE Hosts");list.add(new View(h,s));}return list;}
    private PublicMigrationDestination(List<View> views,PaperSettings s){
        super(views,new PowerVmSelectionPolicyRandomSelection(),s.trigger);this.views=views;this.s=s;power=new SupplyPowerModel(s);
        if(s.destination.equals("legacy"))throw new IllegalArgumentException("Public destination adapter requires explicit cloudsim_min_power or ups_min_power");}
    @Override protected boolean isHostOverUtilizedAfterAllocation(PowerHost host,Vm vm){
        // Equivalent threshold calculation without vmCreate/vmDestroy changing the live VM's owner.
        return ((View)host).requested+vm.getCurrentRequestedTotalMips()/s.hostMips>s.trigger;}
    @Override protected double getUtilizationOfCpuMips(PowerHost host){return ((View)host).cpu*s.hostMips;}
    private int choose(Vm vm,Set<Integer> excluded){
        if(s.destination.equals("cloudsim_min_power")){
            Set<Host> hosts=new HashSet<>();for(int id:excluded)hosts.add(views.get(id));nativeCalls++;
            PowerHost target=super.findHostForVm(vm,hosts);return target==null?-1:target.getId();
        }
        int target=-1;double best=Double.POSITIVE_INFINITY;
        for(View h:views)if(!excluded.contains(h.getId())&&h.isSuitableForVm(vm)
                &&(h.cpu==0||!isHostOverUtilizedAfterAllocation(h,vm))){
            double requested=h.requested,cpu=h.cpu;int entries=h.entries;
            h.reserve(vm,1);double score=totalPower();h.reserve(vm,-1);h.requested=requested;h.cpu=cpu;h.entries=entries;
            if(score<best-1e-9){target=h.getId();best=score;}
        }return target;
    }
    private double totalPower(){double server=0,loss=0;double[] rack=new double[s.racks];
        for(View h:views){double p=h.getPower();server+=p;rack[h.getId()/(s.hosts/s.racks)]+=p;}
        for(double p:rack){if(p>s.rated+1e-7)return Double.POSITIVE_INFINITY;loss+=power.loss(p);}return server+loss;}
    private static boolean busy(Host h){for(Vm v:h.getVmList())if(v.isInMigration())return true;return false;}
    private static Set<Integer> unavailable(List<? extends Host> hosts,PaperSettings s){Set<Integer> ids=new HashSet<>();
        for(Host h:hosts)if(busy(h)||((HostDynamicWorkload)h).getUtilizationOfCpu()>s.trigger+1e-8)ids.add(h.getId());return ids;}
    public static int[] overload(List<? extends Vm> vms,List<? extends Host> hosts,List<Integer> selected,PaperSettings s){
        int[] next=new int[vms.size()];for(Vm v:vms)next[v.getId()]=v.getHost().getId();
        PublicMigrationDestination policy=new PublicMigrationDestination(snapshot(hosts,s),s);Set<Integer> excluded=unavailable(hosts,s);
        for(int i:selected)excluded.add(next[i]);List<Integer> order=new ArrayList<>(selected);
        order.sort((a,b)->Double.compare(vms.get(b).getCurrentRequestedTotalMips(),vms.get(a).getCurrentRequestedTotalMips()));
        for(int i:order){Vm vm=vms.get(i);if(vm.getCurrentRequestedTotalMips()<=1e-8)continue;
            View source=policy.views.get(next[i]);double cpu=source.cpu,requested=source.requested;source.reserve(vm,-1);
            int target=policy.choose(vm,excluded);
            if(target<0){source.reserve(vm,1);source.cpu=cpu;source.requested=requested;continue;}
            next[i]=target;policy.views.get(target).reserve(vm,1);excluded.add(target); // one reserved endpoint per overload move
        }return next;
    }
    public static List<Map<String,Object>> underload(List<? extends Vm> vms,List<? extends Host> hosts,
            List<Map<String,Object>> overload,PaperSettings s){
        Set<Integer> excluded=unavailable(hosts,s);for(Map<String,Object> x:overload){excluded.add(((Host)x.get("source")).getId());excluded.add(((Host)x.get("host")).getId());}
        Host source=null;double minimum=1;
        for(Host h:hosts){double u=((HostDynamicWorkload)h).getUtilizationOfCpu();if(u==0)excluded.add(h.getId());
            else if(!excluded.contains(h.getId())&&u<minimum){source=h;minimum=u;}}
        if(source==null)return Collections.emptyList();excluded.add(source.getId());List<Vm> selected=new ArrayList<>();
        for(Vm v:source.getVmList())if(v.getHost()==source)selected.add(v);
        selected.sort((a,b)->Double.compare(b.getCurrentRequestedTotalMips(),a.getCurrentRequestedTotalMips()));
        PublicMigrationDestination policy=new PublicMigrationDestination(snapshot(hosts,s),s);
        for(Vm v:selected)policy.views.get(source.getId()).reserve(v,-1);
        List<Map<String,Object>> moves=new ArrayList<>();
        for(Vm v:selected){int target=policy.choose(v,excluded);if(target<0)return Collections.emptyList();
            policy.views.get(target).reserve(v,1);Map<String,Object> move=new HashMap<>();move.put("vm",v);
            move.put("source",source);move.put("host",hosts.get(target));move.put("reason","framework_underload_reconstruction");moves.add(move);
        }return moves;
    }
    private static final class DemandVm extends Vm {
        final double demand;DemandVm(int id,double demand,PaperSettings s){super(id,1,s.hostMips,1,s.vmRam,1000,1000,"Xen",new CloudletSchedulerTimeShared());this.demand=demand;}
        @Override public List<Double> getCurrentRequestedMips(){return Arrays.asList(demand);}
        @Override public double getCurrentRequestedTotalMips(){return demand;}
    }
    public static void main(String[] args) throws Exception {
        org.cloudbus.cloudsim.core.CloudSim.init(1,Calendar.getInstance(),false);Log.disable();
        PaperSettings s=new PaperSettings(Paths.get("paper_alignment/config/main.properties")).with("racks","2").with("hosts","6");
        List<PaperHost> hosts=new ArrayList<>();for(int h=0;h<6;h++)hosts.add(new PaperHost(h,s));
        double[] d={.6,.35,.2,.8,.2};int[] old={0,0,1,2,3};List<Vm> vms=new ArrayList<>();
        for(int i=0;i<d.length;i++){Vm v=new DemandVm(i,d[i]*s.hostMips,s);if(!hosts.get(old[i]).vmCreate(v))throw new AssertionError("Fixture allocation");vms.add(v);}
        for(PaperHost h:hosts)h.updateVmsProcessing(0);long before=nativeCalls;
        int[] nativePlan=overload(vms,hosts,Arrays.asList(1),s.with("migration.destination","cloudsim_min_power"));
        int[] upsPlan=overload(vms,hosts,Arrays.asList(1),s.with("migration.destination","ups_min_power"));
        if(nativePlan[1]!=1||upsPlan[1]!=3||nativeCalls<=before)throw new AssertionError("Native tie/UPS rack choice "+nativePlan[1]+"/"+upsPlan[1]);
        for(int i=0;i<vms.size();i++)if(vms.get(i).getHost()!=hosts.get(old[i]))throw new AssertionError("Snapshot changed live owner");
        PublicMigrationDestination noTarget=new PublicMigrationDestination(snapshot(hosts,s),s.with("migration.destination","cloudsim_min_power"));
        if(noTarget.choose(vms.get(1),new HashSet<>(Arrays.asList(0,1,2,3,4,5)))!=-1)throw new AssertionError("Excluded destination");
        hosts.get(1).getVmList().get(0).setInMigration(true);
        if(overload(vms,hosts,Arrays.asList(1),s.with("migration.destination","cloudsim_min_power"))[1]!=3)throw new AssertionError("Busy target selected");
        hosts.get(1).getVmList().get(0).setInMigration(false);
        Vm zero=new DemandVm(5,0,s);if(!hosts.get(4).vmCreate(zero))throw new AssertionError("Zero VM resident allocation");hosts.get(4).updateVmsProcessing(0);
        PublicMigrationDestination zeroPolicy=new PublicMigrationDestination(snapshot(hosts,s),s.with("migration.destination","cloudsim_min_power"));
        if(zeroPolicy.choose(vms.get(1),new HashSet<>(Arrays.asList(0,1,2,3,5)))!=4)throw new AssertionError("Zero CPU resident host unavailable");
        System.out.println("PASS original CloudSim finder, UPS extension, live-state isolation, busy/excluded targets and zero-CPU resident host");
    }
}
