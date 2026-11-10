package repro;
import java.util.*;
import org.cloudbus.cloudsim.*;

/** Compilable innovation entry example; delegates to the verified controller before local changes. */
public final class ResearchExampleController implements ResearchPolicy.Controller {
    private final ResearchPolicy.HysteresisController reference=new ResearchPolicy.HysteresisController();
    private ResearchConfig config;
    public void initialize(ResearchConfig supplied,long seed){
        config=supplied.with("research.controller","consolidation");reference.initialize(config,seed);
    }
    public List<Map<String,Object>> propose(List<? extends Vm> vms,List<? extends Host> hosts,ResearchConfig supplied){
        // Replace this method with your proposed selection and destination strategy.
        // Return maps with vm/source/host/reason; the execution engine enforces physical constraints.
        return reference.propose(vms,hosts,config);
    }
}
