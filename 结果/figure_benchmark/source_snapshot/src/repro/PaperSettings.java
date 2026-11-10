package repro;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Runtime configuration, shared by planning, execution and independent audit. */
public final class PaperSettings {
    public final Properties values=new Properties();
    public final int hosts,racks,step,population,generations,hostRam,vmRam;
    public final double hostMips,idle,max,trigger,packingCap,rated,factor,a0,a1,a2,cross,mutation;
    public final long bandwidth,storage; public final double[] vmTypes;
    public final boolean totalObjective; public final String controller,destination;
    public PaperSettings(Path path) throws IOException { this(read(path)); }
    private static Properties read(Path p) throws IOException {
        Properties v=new Properties();try(Reader r=Files.newBufferedReader(p)){v.load(r);}return v;
    }
    public PaperSettings(Properties p) {
        values.putAll(p);hosts=i("hosts",100);racks=i("racks",5);step=i("step.seconds",300);
        population=i("population",40);generations=i("generations",60);hostRam=i("host.ram.mb",65536);
        vmRam=i("vm.ram.mb",512);hostMips=d("host.mips",2500);idle=d("host.idle.w",218.3);
        max=d("host.max.w",350);trigger=d("cpu.trigger",.9);packingCap=d("packing.cap",.9);
        rated=d("ups.usable.w",7000);factor=d("ups.factor",1.25);
        a0=d("ups.a0",.0549);a1=d("ups.a1",.0077);a2=d("ups.a2",.0207);
        cross=d("crossover",.8);mutation=d("mutation",.05);
        bandwidth=Long.parseLong(values.getProperty("host.bandwidth.kbps","1000000"));
        storage=Long.parseLong(values.getProperty("host.storage.mb","1000000"));
        String objective=values.getProperty("genetic.objective","total");
        if(!objective.equals("total")&&!objective.equals("server_only"))throw new IllegalArgumentException("Unknown genetic.objective");
        totalObjective=objective.equals("total");controller=values.getProperty("controller","threshold");
        if(!Arrays.asList("threshold","none","periodic_extension","framework_underload").contains(controller))throw new IllegalArgumentException("Unknown controller");
        destination=values.getProperty("migration.destination","legacy");
        if(!Arrays.asList("legacy","cloudsim_min_power","ups_min_power").contains(destination))throw new IllegalArgumentException("Unknown migration.destination: "+destination);
        if(!destination.equals("legacy")&&controller.equals("periodic_extension"))throw new IllegalArgumentException("Public destination requires threshold or framework_underload controller");
        values.setProperty("migration.destination",destination);
        vmTypes=Arrays.stream(values.getProperty("vm.mips","2500,2000,1000,500").split(",")).mapToDouble(Double::parseDouble).toArray();
        values.setProperty("host.bandwidth.kbps",""+bandwidth);values.setProperty("host.storage.mb",""+storage);
        values.setProperty("vm.mips",values.getProperty("vm.mips","2500,2000,1000,500"));
        values.setProperty("genetic.objective",objective);values.setProperty("controller",controller);
        if(hosts<=0||racks<=0||hosts%racks!=0||step<=0||population<2||generations<0||hostRam<vmRam||vmRam<=0
                ||bandwidth<=0||storage<1000||hostMips<=0||idle<0||max<idle||trigger<=0||trigger>1
                ||packingCap<=0||packingCap>1||rated<=0||factor<1||a0<0||a1<0||a2<0||cross<0||cross>1||mutation<0||mutation>1)
            throw new IllegalArgumentException("Invalid physical, UPS or algorithm parameters");
        for(double m:vmTypes)if(!Double.isFinite(m)||m<=0||m>hostMips)throw new IllegalArgumentException("VM exceeds PE MIPS");
        for(Object key:values.keySet()) {
            String s=values.getProperty(key.toString());
            if(s.equals("NaN")||s.equals("Infinity"))throw new IllegalArgumentException("Nonfinite parameter "+key);
        }
    }
    private int i(String k,int fallback){int v=Integer.parseInt(values.getProperty(k,""+fallback));values.setProperty(k,""+v);return v;}
    private double d(String k,double fallback){double v=Double.parseDouble(values.getProperty(k,""+fallback));
        if(!Double.isFinite(v))throw new IllegalArgumentException("Nonfinite "+k);values.setProperty(k,""+v);return v;}
    public PaperSettings with(String key,String val){Properties p=new Properties();p.putAll(values);p.setProperty(key,val);return new PaperSettings(p);}
    public double vmMips(int index){return vmTypes[index%vmTypes.length];}
    public void save(Path path) throws IOException {try(Writer w=Files.newBufferedWriter(path)){values.store(w,"Actual runtime parameters; unspecified values are reconstructed assumptions");}}
    public static void main(String[] args) throws Exception {
        PaperSettings s=new PaperSettings(Paths.get("paper_alignment/config/main.properties"));
        if(s.hosts!=100||s.racks!=5||s.trigger!=.9)throw new AssertionError("Paper configuration");
        try{s.with("host.mips","NaN");throw new AssertionError("NaN accepted");}catch(IllegalArgumentException expected){}
        if(!s.destination.equals("legacy"))throw new AssertionError("Historical baseline default changed");
        try{s.with("migration.destination","unknown");throw new AssertionError("Unknown destination accepted");}catch(IllegalArgumentException expected){}
        s.with("migration.destination","cloudsim_min_power");s.with("migration.destination","ups_min_power");
        System.out.println("PASS runtime configuration and physical bounds");
    }
}
