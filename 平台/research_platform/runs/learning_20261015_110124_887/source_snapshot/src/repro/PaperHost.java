package repro;
import java.util.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.power.PowerHost;
import org.cloudbus.cloudsim.provisioners.*;

/** Real scheduler allocation; migrating-in replica consumes CPU but never processes its Cloudlet. */
public final class PaperHost extends PowerHost {
    public final PaperSettings s;public final SupplyPowerModel model;
    public PaperHost(int id,PaperSettings s){this(id,s,Arrays.asList(new Pe(0,new PeProvisionerSimple(s.hostMips))));}
    private PaperHost(int id,PaperSettings s,List<Pe> pes){super(id,new RamProvisionerSimple(s.hostRam),
            new BwProvisionerSimple(s.bandwidth),s.storage,pes,new VmSchedulerTimeSharedOverSubscription(pes),new SupplyPowerModel(s));
        this.s=s;model=new SupplyPowerModel(s);}
    @Override public double updateVmsProcessing(double time){
        for(Vm vm:this.<Vm>getVmList())if(vm.getHost()==this)vm.updateVmProcessing(time,getVmScheduler().getAllocatedMipsForVm(vm));
        for(Vm vm:this.<Vm>getVmList())getVmScheduler().deallocatePesForVm(vm);
        for(Vm vm:this.<Vm>getVmList())getVmScheduler().allocatePesForVm(vm,vm.getCurrentRequestedMips());
        double cpu=0;
        for(Vm vm:this.<Vm>getVmList()){
            double allocated=getVmScheduler().getTotalAllocatedMipsForVm(vm);
            if(vm.getHost()==this&&vm.isInMigration())allocated/=.9; // source CPU includes copying overhead, per official PowerHost model.
            cpu+=allocated;
        }
        setPreviousUtilizationMips(getUtilizationMips());setUtilizationMips(cpu);return Double.MAX_VALUE;
    }
    @Override public double getPower(){return model.host(Math.min(1,getUtilizationOfCpu()),!getVmList().isEmpty());}
    public double serviceMips(){double v=0;for(Vm vm:this.<Vm>getVmList())if(vm.getHost()==this)v+=getVmScheduler().getTotalAllocatedMipsForVm(vm);return v;}
    public double requestedMips(){double v=0;for(Vm vm:this.<Vm>getVmList())if(vm.getHost()==this)v+=vm.getCurrentRequestedTotalMips();return v;}
    public static void main(String[] args) throws Exception {
        org.cloudbus.cloudsim.core.CloudSim.init(1,Calendar.getInstance(),false);
        PaperSettings s=new PaperSettings(java.nio.file.Paths.get("paper_alignment/config/main.properties"));
        PaperHost h=new PaperHost(0,s);if(h.getPower()!=0)throw new AssertionError("Empty host not asleep");
        System.out.println("PASS PowerHost initialization, actual scheduler and empty-host power");
    }
}
