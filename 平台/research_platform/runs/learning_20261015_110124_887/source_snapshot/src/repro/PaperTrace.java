package repro;
import org.cloudbus.cloudsim.UtilizationModel;
/** Sample index changes only after processing the previous interval at a trace boundary. */
public final class PaperTrace implements UtilizationModel {
    public final double[] samples;private int index;
    public PaperTrace(double[] samples){this.samples=samples.clone();for(double x:samples)if(!Double.isFinite(x)||x<0||x>1)throw new IllegalArgumentException("CPU trace outside [0,1]");}
    public void sample(int i){if(i<0||i>=samples.length)throw new IllegalArgumentException("Trace sample "+i);index=i;}
    public double getUtilization(double time){return samples[index];}
    public static void main(String[] args){PaperTrace t=new PaperTrace(new double[]{.1,.9});
        if(t.getUtilization(300)!=.1)throw new AssertionError("Future sample leaked into previous work interval");t.sample(1);
        if(t.getUtilization(300)!=.9)throw new AssertionError("sample");System.out.println("PASS explicit trace boundary");}
}
