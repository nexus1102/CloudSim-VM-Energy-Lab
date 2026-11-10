package repro;
import java.nio.file.*;
import java.lang.reflect.*;
public final class MatrixAcceptance {
    public static void main(String[] args) throws Exception {
        ResearchConfig base=new ResearchConfig(Paths.get("research_platform/config/default.properties"));
        ResearchExperiments.validateMatrix(base);
        for(String[] pair:new String[][]{{"hosts","200"},{"generations","12"},{"packing.cap","1"},{"research.initialization","random_hosts"}}) {
            try {ResearchExperiments.validateMatrix(base.with(pair[0],pair[1]));throw new AssertionError("Unsupported Matrix accepted");}
            catch(IllegalArgumentException expected) { }
        }
        Path out=Paths.get(args[0]);Files.createDirectories(out.resolve("inputs"));
        Path input=out.resolve("inputs/static_30.csv");Files.copy(Paths.get("correction/inputs/static_30.csv"),input);
        Method benchmark=ResearchExperiments.class.getDeclaredMethod("benchmark",Path.class,ResearchConfig.class,Path.class);
        benchmark.setAccessible(true);benchmark.invoke(null,out,base,input);
        System.out.println("PASS fixed-matrix rejection and 27 real benchmark trajectories");
    }
}
