package repro;
import java.util.*;
import org.cloudbus.cloudsim.power.models.PowerModel;

/** Explicit supply input/output/loss and host power, parameterized per paper case. */
public final class SupplyPowerModel implements PowerModel {
    public final PaperSettings s;
    public SupplyPowerModel(PaperSettings s){this.s=s;}
    public double getPower(double u){if(!Double.isFinite(u)||u<0||u>1+1e-8)throw new IllegalArgumentException("Physical CPU "+u);
        return s.idle+(s.max-s.idle)*Math.min(1,u);}
    public double host(double u,boolean awake){if(!awake&&u>1e-8)throw new IllegalArgumentException("Sleeping host has workload");return awake?getPower(u):0;}
    public double loss(double output){if(!Double.isFinite(output)||output<0||output>s.rated+1e-7)
            throw new IllegalArgumentException("UPS output "+output+" exceeds usable "+s.rated);
        double installed=s.rated*s.factor,x=output/installed;
        return installed*(s.a0*x*x+s.a1*x+s.a2);}
    public double[] powers(double[] d,int[] plan){double[] u=new double[s.hosts];boolean[] awake=new boolean[s.hosts];
        if(d.length!=plan.length)throw new IllegalArgumentException("VM mapping length");
        for(int i=0;i<d.length;i++){if(plan[i]<0||plan[i]>=s.hosts||!Double.isFinite(d[i])||d[i]<0)throw new IllegalArgumentException("Invalid VM "+i);
            u[plan[i]]+=d[i];awake[plan[i]]=true;}
        double[] rack=new double[s.racks];double server=0,ups=0;
        for(int h=0;h<s.hosts;h++){double p=host(u[h],awake[h]);server+=p;rack[h/(s.hosts/s.racks)]+=p;}
        for(double p:rack)ups+=loss(p);return new double[]{server,ups,server+ups};}
    public double score(double[] d,int[] plan,boolean total){try{return powers(d,plan)[total?2:0];}
        catch(IllegalArgumentException infeasible){return Double.POSITIVE_INFINITY;}}
    public static int[] figure14(){return new int[]{5,5,5,5,0,0,0,0,1,1,1,0,1,6,5,6,6,6,6,7};}
    public static void close(double a,double b){if(Math.abs(a-b)>1e-7)throw new AssertionError(a+" != "+b);}
    public static void main(String[] args) throws Exception {
        SupplyPowerModel m=new SupplyPowerModel(new PaperSettings(java.nio.file.Paths.get("paper_alignment/config/platform.properties")));
        close(m.host(0,true),218);close(m.host(1,true),350);close(m.loss(0),123.4);close(m.loss(900),164.9305);
        if(figure14()[11]!=0||figure14()[12]!=1)throw new AssertionError("Figure 2-14 VM12/VM13");
        System.out.println("PASS separate platform model, UPS endpoints and corrected Figure 2-14");
    }
}
