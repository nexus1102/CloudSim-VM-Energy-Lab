package repro;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Canonical physical coefficients and explicit modular redundancy, compiled exactly to a polynomial. */
public final class ResearchConfig {
    public final Properties original=new Properties();
    public final PaperSettings settings;
    public final String topology,controller,initialization,plugin;
    public final int required,active,lowSamples;
    public final double moduleRated,quadratic,linear,constant,standby,endpointW,lowThreshold,cooldown;
    public final boolean bfdSeed;
    public ResearchConfig(Path path)throws IOException {this(read(path));}
    private static Properties read(Path p)throws IOException {
        Properties x=new Properties();try(Reader r=Files.newBufferedReader(p,java.nio.charset.StandardCharsets.UTF_8)){x.load(r);}return x;
    }
    public ResearchConfig(Properties source) {
        original.putAll(source);
        for(String k:new String[]{"ups.a0","ups.a1","ups.a2","ups.factor"})if(original.containsKey(k))
            throw new IllegalArgumentException("Use ups.loss.quadratic/linear/constant and explicit topology, not ambiguous "+k);
        topology=text("ups.topology","n_plus_1_standby");required=integer("ups.required.modules",4);
        moduleRated=number("ups.module.rated.w",2000);quadratic=number("ups.loss.quadratic",.0549);
        linear=number("ups.loss.linear",.0077);constant=number("ups.loss.constant",.0207);
        standby=number("ups.standby.loss.w",0);endpointW=number("migration.incremental.w.per.endpoint",0);
        controller=text("research.controller","consolidation");initialization=text("research.initialization","random_hosts");
        plugin=text("research.controller.class","");bfdSeed=bool("research.bfd.seed",false);
        lowThreshold=number("research.underload.threshold",.3);lowSamples=integer("research.underload.samples",3);
        cooldown=number("research.underload.cooldown.seconds",900);
        double snap=number("scheduler.request.snap.epsilon.mips",1e-8);
        if(snap<0||snap>1e-6)throw new IllegalArgumentException("Request roundoff guard must be between 0 and 1e-6 MIPS");
        if(!Arrays.asList("single","n_plus_1_standby","n_plus_1_shared","two_n").contains(topology))throw new IllegalArgumentException("Unknown UPS topology "+topology);
        if(!Arrays.asList("threshold","consolidation","none","custom").contains(controller))throw new IllegalArgumentException("Unknown research.controller");
        if(controller.equals("custom")&&plugin.isEmpty())throw new IllegalArgumentException("Custom controller requires research.controller.class");
        if(!Arrays.asList("random_hosts","feasible_packing").contains(initialization))throw new IllegalArgumentException("Unknown initialization");
        if(required<1||required>100000||moduleRated<=0||quadratic<0||linear<0||constant<0||standby<0||endpointW<0
                ||lowThreshold<=0||lowThreshold>=1||lowSamples<1||cooldown<0)throw new IllegalArgumentException("Invalid modular UPS, hardware or underload parameters");
        if(topology.equals("single")&&required!=1)throw new IllegalArgumentException("Single topology requires one module");
        if(!topology.equals("n_plus_1_standby")&&standby!=0)throw new IllegalArgumentException("Standby watts apply only to n_plus_1_standby");
        active=topology.equals("two_n")?2*required:topology.equals("n_plus_1_shared")?required+1:required;
        if(!original.containsKey("ups.usable.w"))original.setProperty("ups.usable.w","7500");
        if(!original.containsKey("host.pes"))original.setProperty("host.pes","1");
        if(integer("host.pes",1)!=1)throw new IllegalArgumentException("This verified engine supports one PE per Host; aggregate MIPS explicitly");
        Properties compiled=new Properties();compiled.putAll(original);
        double usable=number("ups.usable.w",7500),normalRating=active*moduleRated;
        // L(P)=q P^2/(active*S_m)+l P+c active*S_m+standby. S=usable in legacy engine.
        compiled.setProperty("ups.factor","1");compiled.setProperty("ups.a0",""+(quadratic*usable/normalRating));
        compiled.setProperty("ups.a1",""+linear);compiled.setProperty("ups.a2",""+((constant*normalRating+standby)/usable));
        compiled.setProperty("genetic.objective",text("genetic.objective","server_only"));
        compiled.setProperty("migration.destination",text("migration.destination","cloudsim_min_power"));
        compiled.setProperty("controller",controller.equals("none")?"none":controller.equals("consolidation")?"framework_underload":"threshold");
        settings=new PaperSettings(compiled);
        if(usable>required*moduleRated+1e-8)throw new IllegalArgumentException("Usable output exceeds required module capacity/failover capacity");
        if(usable+1e-8<(settings.hosts/settings.racks)*(settings.max+endpointW))
            throw new IllegalArgumentException("UPS usable watts must cover full Host load plus configured incremental endpoint watts");
        if(lowThreshold>=settings.trigger)throw new IllegalArgumentException("Underload threshold must be below overload trigger");
    }
    private String text(String k,String v){String result=original.getProperty(k,v).trim();original.setProperty(k,result);return result;}
    private int integer(String k,int v){return Integer.parseInt(text(k,""+v));}
    private double number(String k,double v){double result=Double.parseDouble(text(k,""+v));
        if(!Double.isFinite(result))throw new IllegalArgumentException("Nonfinite "+k);return result;}
    private boolean bool(String k,boolean v){String result=text(k,""+v);if(!result.equals("true")&&!result.equals("false"))throw new IllegalArgumentException("Boolean required: "+k);return Boolean.parseBoolean(result);}
    public ResearchConfig with(String k,String v){Properties p=new Properties();p.putAll(original);p.setProperty(k,v);return new ResearchConfig(p);}
    public double loss(double output){
        if(!Double.isFinite(output)||output<0||output>settings.rated+1e-7)throw new IllegalArgumentException("UPS output outside usable capacity");
        double each=output/active;return active*(quadratic*each*each/moduleRated+linear*each+constant*moduleRated)+standby;
    }
    public void save(Path p)throws IOException {try(Writer w=Files.newBufferedWriter(p,java.nio.charset.StandardCharsets.UTF_8)){original.store(w,"Physical research parameters: assumptions are explicit, not author-confirmed");}}
    public static void main(String[] args)throws Exception {
        ResearchConfig b=new ResearchConfig(Paths.get("research_platform/config/default.properties"));
        for(String t:new String[]{"n_plus_1_standby","n_plus_1_shared","two_n"}) {
            ResearchConfig c=b.with("ups.topology",t);SupplyPowerModel mapped=new SupplyPowerModel(c.settings);
            for(double p:new double[]{0,900,3500,7000,7500})SupplyPowerModel.close(c.loss(p),mapped.loss(p));
        }
        ResearchConfig cold=b.with("ups.standby.loss.w","20");SupplyPowerModel.close(cold.loss(3500)-b.loss(3500),20);
        ResearchConfig literal=new ResearchConfig(Paths.get("research_platform/config/paper_validation_literal.properties"));
        SupplyPowerModel.close(literal.loss(0),123.4);SupplyPowerModel.close(literal.loss(900),164.9305);
        for(String[] bad:new String[][]{{"ups.loss.quadratic","NaN"},{"ups.required.modules","0"},{"migration.incremental.w.per.endpoint","100"},{"ups.a0",".1"}}) {
            try{b.with(bad[0],bad[1]);throw new AssertionError("Invalid research parameter accepted");}catch(IllegalArgumentException expected){}
        }
        System.out.println("PASS modular UPS exact mapping, standby, literal table contradiction and physical parameter bounds");
    }
}
