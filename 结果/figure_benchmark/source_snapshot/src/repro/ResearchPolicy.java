package repro;
import java.util.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.core.CloudSim;
import org.cloudbus.cloudsim.power.*;

/** Pluggable online controller; execution checks remain in the DataCenter. */
public final class ResearchPolicy extends PowerVmAllocationPolicyAbstract {
    public interface Controller {
        default void initialize(ResearchConfig config,long seed) { }
        List<Map<String,Object>> propose(List<? extends Vm> vms,List<? extends Host> hosts,ResearchConfig config);
        default void completed(Vm vm,Host source,Host target,double time) { }
    }
    private final ResearchConfig cfg;private final Controller control;private int[] initial;
    public ResearchPolicy(List<? extends Host> hosts,ResearchConfig cfg,long seed)throws Exception {
        super(hosts);this.cfg=cfg;
        if(cfg.controller.equals("custom")) {
            Object plugin=Class.forName(cfg.plugin).getDeclaredConstructor().newInstance();
            if(!(plugin instanceof Controller))throw new IllegalArgumentException("Configured class must implement ResearchPolicy.Controller: "+cfg.plugin);
            control=(Controller)plugin;
        } else control=new HysteresisController();
        control.initialize(cfg,seed);
    }
    public void initial(int[] p){initial=p.clone();for(int h:p)if(h<0||h>=getHostList().size())throw new IllegalArgumentException("Initial Host ID outside configured range");}
    @Override public PowerHost findHostForVm(Vm vm){return initial==null?null:(PowerHost)getHostList().get(initial[vm.getId()]);}
    @Override public boolean allocateHostForVm(Vm vm){if(initial==null)throw new IllegalStateException("Initial VM mapping missing");return allocateHostForVm(vm,findHostForVm(vm));}
    @Override public boolean allocateHostForVm(Vm vm,Host host){if(!host.vmCreate(vm))return false;getVmTable().put(vm.getUid(),host);return true;}
    @Override public void deallocateHostForVm(Vm vm){Host host=getVmTable().remove(vm.getUid());if(host!=null)host.vmDestroy(vm);}
    @Override public Host getHost(Vm vm){return getVmTable().get(vm.getUid());}
    @Override public Host getHost(int id,int user){return getVmTable().get(Vm.getUid(user,id));}
    @Override public List<Map<String,Object>> optimizeAllocation(List<? extends Vm> vms){
        if(cfg.controller.equals("none"))return Collections.emptyList();
        List<Map<String,Object>> moves=control.propose(vms,getHostList(),cfg);
        if(moves==null)throw new IllegalArgumentException("Controller returned null migration plan");return moves;
    }
    public void completed(Vm vm,Host source,Host target,double time){control.completed(vm,source,target,time);}
    private static boolean busy(Host h){for(Vm v:h.getVmList())if(v.isInMigration())return true;return false;}
    /** Deliberate engineering choice: one random overload VM, one sustained-low source, global cooldown. */
    public static final class HysteresisController implements Controller {
        private Random random;private int[] low;private double lastEvacuationProposal=Double.NEGATIVE_INFINITY;
        public void initialize(ResearchConfig c,long seed){random=new Random(seed);low=new int[c.settings.hosts];}
        public List<Map<String,Object>> propose(List<? extends Vm> vms,List<? extends Host> hosts,ResearchConfig c) {
            PaperSettings s=c.settings;List<Integer> selected=new ArrayList<>();
            for(Host h:hosts){double u=((HostDynamicWorkload)h).getUtilizationOfCpu();
                low[h.getId()]=!busy(h)&&!h.getVmList().isEmpty()&&u<c.lowThreshold?Math.min(c.lowSamples,low[h.getId()]+1):0;
                if(busy(h)||u<=s.trigger+1e-8)continue;
                List<Vm> candidates=new ArrayList<>();for(Vm v:h.getVmList())if(v.getHost()==h&&!v.isInMigration())candidates.add(v);
                if(!candidates.isEmpty())selected.add(candidates.get(random.nextInt(candidates.size())).getId());
            }
            List<Map<String,Object>> result=new ArrayList<>();
            int[] destinations=ResearchDestination.overload(vms,hosts,selected,s);
            Set<Integer> excluded=new HashSet<>();
            for(int id:selected){Vm v=vms.get(id);int target=destinations[id];if(target==v.getHost().getId())continue;
                Map<String,Object> m=new HashMap<>();m.put("vm",v);m.put("source",v.getHost());m.put("host",hosts.get(target));m.put("reason","over90_random_one");result.add(m);
                excluded.add(v.getHost().getId());excluded.add(target);
            }
            double time=CloudSim.clock();
            if(!c.controller.equals("consolidation")||time-lastEvacuationProposal<c.cooldown)return result;
            Host minimum=null;double cpu=Double.POSITIVE_INFINITY;
            for(Host h:hosts)if(!busy(h)&&!excluded.contains(h.getId())&&!h.getVmList().isEmpty()) {
                double u=((HostDynamicWorkload)h).getUtilizationOfCpu();if(u<cpu){cpu=u;minimum=h;}
            }
            if(minimum!=null&&low[minimum.getId()]>=c.lowSamples) {
                List<Map<String,Object>> evacuation=ResearchDestination.underload(vms,hosts,result,s);
                if(!evacuation.isEmpty()){result.addAll(evacuation);lastEvacuationProposal=time;low[minimum.getId()]=0;}
            }
            return result;
        }
    }
}
