package repro;

import java.util.*;
import java.io.*;
import java.nio.file.*;
import org.cloudbus.cloudsim.*;
import org.cloudbus.cloudsim.core.*;
import org.cloudbus.cloudsim.provisioners.*;

/** Real CloudSim entities, actual host placement and allocated-MIPS measurement. */
public final class Simulation {
    public static final double MIPS = 2500, ORIGIN = .2;
    public static final int STEP = 300;
    public static final class Stats {
        public double serverKwh, upsKwh, cpuError, powerError;
        public int migrations, samples, created;
        public int activeStart,activeEnd,activeMin=Integer.MAX_VALUE,activeMax,aboveThresholdHostSamples;
        public double activeSum,meanVmCpu,meanPhysicalDemand;
        public double totalKwh() { return serverKwh + upsKwh; }
    }
    public static final class Options {
        public final double[] vmMips;
        public final boolean periodic,hostDetails,stable,uniformMips;
        public Options(double[] vmMips,boolean periodic,boolean hostDetails) {
            this(vmMips,periodic,hostDetails,false);
        }
        public Options(double[] vmMips,boolean periodic,boolean hostDetails,boolean stable) {
            this.vmMips=vmMips.clone();this.periodic=periodic;this.hostDetails=hostDetails;
            this.stable=stable;this.uniformMips=Arrays.stream(vmMips).allMatch(m->m==MIPS);
            for (double m:vmMips) if (!Double.isFinite(m) || m<=0 || m>MIPS)
                throw new IllegalArgumentException("VM MIPS outside physical PE capacity: "+m);
        }
    }
    private Simulation() { }
    public static double[][] read(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path); double[][] matrix = new double[lines.size()][];
        int columns = -1;
        for (int i = 0; i < matrix.length; i++) {
            String[] fields = lines.get(i).split(","); matrix[i] = new double[fields.length];
            if (columns < 0) columns = fields.length;
            if (fields.length != columns) throw new IOException("Nonrectangular CPU data: " + path);
            for (int j = 0; j < fields.length; j++) {
                double v = Double.parseDouble(fields[j]);
                if (!Double.isFinite(v) || v < 0 || v > 1) throw new IOException("CPU outside [0,1]: " + path);
                matrix[i][j] = v;
            }
        }
        if (matrix.length == 0 || columns == 0) throw new IOException("Empty CPU data: " + path);
        return matrix;
    }
    public static final class Trace implements UtilizationModel {
        private final double[] values;
        Trace(double[] values) { this.values = values; }
        public double getUtilization(double time) {
            int idx = Math.max(0, Math.min(values.length-1, (int)Math.floor((time-ORIGIN+1e-6)/STEP)));
            return values[idx]; // zero-order hold, including final endpoint.
        }
    }
    public static final class OnlineScheduler extends CloudletSchedulerDynamicWorkload {
        OnlineScheduler(double vmMips) { super(vmMips,1); }
        long completedMi(Cloudlet c) {
            for (ResCloudlet r:this.<ResCloudlet>getCloudletExecList()) if (r.getCloudletId()==c.getCloudletId())
                return c.getCloudletLength()-r.getRemainingCloudletLength();
            return c.getCloudletFinishedSoFar();
        }
    }
    public static final class Policy extends VmAllocationPolicy {
        private final int[] plan; private final Map<String,Host> table = new HashMap<>();
        Policy(List<HostDynamicWorkload> hosts, int[] plan) { super(hosts); this.plan = plan; }
        public boolean allocateHostForVm(Vm vm) { return allocateHostForVm(vm,getHostList().get(plan[vm.getId()])); }
        public boolean allocateHostForVm(Vm vm, Host host) {
            if (!host.vmCreate(vm)) return false;
            table.put(vm.getUid(),host); return true;
        }
        public void deallocateHostForVm(Vm vm) { Host h = table.remove(vm.getUid()); if (h != null) h.vmDestroy(vm); }
        public Host getHost(Vm vm) { return table.get(vm.getUid()); }
        public Host getHost(int id, int user) { return table.get(Vm.getUid(user,id)); }
        public List<Map<String,Object>> optimizeAllocation(List<? extends Vm> vms) { return Collections.emptyList(); }
    }
    public static final class SupplyDatacenter extends Datacenter {
        SupplyDatacenter(List<HostDynamicWorkload> hosts, Policy policy) throws Exception {
            super("PowerSupplyAwareDatacenter", new DatacenterCharacteristics("x86","Linux","Xen",hosts,
                    8,0,0,0,0),policy,new LinkedList<Storage>(),STEP);
        }
        // External periodic SimEntity drives the trace clock and avoids duplicate automatic ticks.
        @Override protected void updateCloudletProcessing() { }
        void pulse(double time) {
            for (HostDynamicWorkload h : this.<HostDynamicWorkload>getHostList()) h.updateVmsProcessing(time);
            checkCloudletCompletion();
        }
    }
    private static List<HostDynamicWorkload> hosts(int count) {
        List<HostDynamicWorkload> hs = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            List<Pe> pes = Arrays.asList(new Pe(0,new PeProvisionerSimple(MIPS)));
            hs.add(new HostDynamicWorkload(i,new RamProvisionerSimple(1048576),
                    new BwProvisionerSimple(10000000),100000000L,pes,new VmSchedulerTimeSharedOverSubscription(pes)));
        }
        return hs;
    }
    private static int[] insert(double[] demand, int[] original, List<Integer> moved, int hosts,
            String method, PowerModels.Ups ups, int racks, Random rng) {
        double[] fixed = new double[hosts]; boolean[] missing = new boolean[demand.length];
        for (int i : moved) missing[i] = true;
        for (int i = 0; i < demand.length; i++) if (!missing[i]) fixed[original[i]] += demand[i];
        boolean genetic = !method.equals("FFD") && !method.equals("BFD");
        int[] best = null; double bestScore = Double.POSITIVE_INFINITY;
        // Common online repair wrapper. Only selected VMs can move; GA/GGA retain their server objective.
        // BFD-GA uses total supply power. This is an explicit extension, not author source code.
        int population = genetic ? Placement.POP : 1;
        int[][] pop = new int[population][];
        for (int k=0;k<population;k++) { pop[k]=original.clone();
            for (int i:moved) pop[k][i]=genetic?rng.nextInt(hosts):-1; }
        for (int generation=0;generation<=(genetic?Placement.GENERATIONS:0);generation++) {
          double[] scores=new double[population]; int elite=0;
          for (int k=0;k<population;k++) {
            int[] candidate = pop[k].clone(); double[] u = fixed.clone(); boolean feasible = true;
            List<Integer> ids = new ArrayList<>(moved);
            ids.sort((a,b)->Double.compare(demand[b],demand[a]));
            for (int i : ids) {
                List<Integer> options = new ArrayList<>(); int chosen = -1;
                for (int h = 0; h < hosts; h++) if (u[h]+demand[i] <= Math.max(.9,demand[i])+PowerModels.EPS) {
                    options.add(h);
                    if (chosen < 0 || (!method.equals("FFD") && u[h] > u[chosen])) chosen = h;
                }
                if (chosen < 0) { feasible = false; break; }
                if (genetic && options.contains(candidate[i])) chosen=candidate[i];
                candidate[i] = chosen; u[chosen] += demand[i];
            }
            if (!feasible) throw new IllegalStateException("Online chromosome cannot be repaired");
            double[] p = PowerModels.powers(demand,candidate,hosts,racks,ups);
            double score = p[method.equals("BFD-GA") ? 2 : 0];
            if (score < bestScore) { bestScore = score; best = candidate; }
            scores[k]=score; pop[k]=candidate;
            if (scores[k]<scores[elite]) elite=k;
          }
          if (!genetic || generation==Placement.GENERATIONS) break;
          int[][] next=new int[population][]; next[0]=pop[elite].clone();
          double max=Arrays.stream(scores).max().getAsDouble();
          for (int k=1;k<population;k++) {
            int[] parents=new int[2];
            for (int z=0;z<2;z++) {
                double total=0; for (double score:scores) total+=max-score+1e-3;
                double spin=rng.nextDouble()*total; parents[z]=population-1;
                for (int j=0;j<population;j++) if ((spin-=max-scores[j]+1e-3)<=0) { parents[z]=j; break; }
            }
            int[] a=pop[parents[0]],b=pop[parents[1]],child=a.clone();
            boolean grouping=method.equals("GGA");
            if (rng.nextDouble()<Placement.CROSS) {
                int cut=rng.nextInt(moved.size()),group=b[moved.get(cut)];
                for (int z=0;z<moved.size();z++) if (grouping?b[moved.get(z)]==group:z>=cut)
                    child[moved.get(z)]=b[moved.get(z)];
            }
            if (grouping && rng.nextDouble()<Placement.MUTATION) {
                int group=child[moved.get(rng.nextInt(moved.size()))];
                for (int i:moved) if (child[i]==group) child[i]=-1;
            } else if (!grouping) for (int i:moved) if (rng.nextDouble()<Placement.MUTATION) child[i]=rng.nextInt(hosts);
            next[k]=child;
          }
          pop=next;
        }
        if (best == null) throw new IllegalStateException("No feasible online placement within physical CPU capacity");
        return best;
    }
    public static final class Meter extends SimEntity {
        private final SupplyDatacenter dc; private final Policy policy; private final List<Vm> vms;
        private final double[][] trace; private final int racks; private final PowerModels.Ups ups;
        private final String method; private final Random rng; private final boolean dynamic;
        private final Options options; private final long seed;
        private final PrintWriter times, details; private final Stats stats; private int index = 0;
        Meter(SupplyDatacenter dc, Policy policy, List<Vm> vms, double[][] trace, int racks,
                PowerModels.Ups ups, String method, long seed, boolean dynamic,
                PrintWriter times, PrintWriter details, Stats stats,Options options) {
            super("UPS_Meter"); this.dc=dc; this.policy=policy; this.vms=vms; this.trace=trace;
            this.racks=racks; this.ups=ups; this.method=method; rng=new Random(seed); this.dynamic=dynamic;
            this.times=times; this.details=details; this.stats=stats;
            this.options=options;this.seed=seed;
        }
        public void startEntity() { schedule(getId(),ORIGIN,9100); }
        public void shutdownEntity() { }
        public void processEvent(SimEvent event) {
            int n = trace[0].length;
            if (index >= n) { dc.pulse(CloudSim.clock()); CloudSim.stopSimulation(); return; }
            double[] d = new double[vms.size()]; int[] p = new int[d.length];
            for (int i = 0; i < d.length; i++) {
                if (vms.get(i).getHost()==null) throw new IllegalStateException("VM creation failed: " + i);
                d[i]=options.uniformMips?trace[i][index]:trace[i][index]*vms.get(i).getMips()/MIPS;
                p[i]=vms.get(i).getHost().getId();
            }
            double[] load = Placement.loads(d,p,dc.getHostList().size());
            List<Integer> moved = new ArrayList<>();
            if (dynamic && !options.periodic) for (int h = 0; h < load.length; h++) while (load[h] > .9+PowerModels.EPS) {
                List<Integer> ids = new ArrayList<>();
                for (int i=0;i<p.length;i++) if (p[i]==h && !moved.contains(i)) ids.add(i);
                if (ids.isEmpty()) throw new IllegalStateException("Overloaded host has no removable VM");
                int i=ids.get(rng.nextInt(ids.size())); moved.add(i); load[h]-=d[i];
            }
            if (dynamic && options.periodic) {
                dc.pulse(CloudSim.clock());
                int[] next=DynamicController.replan(method,d,p,load.length,racks,ups,seed+index*1000003L,options.stable);
                for (int i=0;i<p.length;i++) if (next[i]!=p[i]) moved.add(i);
                for (int i:moved) policy.deallocateHostForVm(vms.get(i));
                for (int i:moved) if (!policy.allocateHostForVm(vms.get(i),dc.getHostList().get(next[i])))
                    throw new IllegalStateException("Periodic VM placement failed: "+i);
                stats.migrations+=moved.size();p=next;
            } else if (!moved.isEmpty()) {
                // Account old processing up to boundary before transferring VMs.
                dc.pulse(CloudSim.clock());
                int[] next = insert(d,p,moved,load.length,method,ups,racks,rng);
                for (int i : moved) policy.deallocateHostForVm(vms.get(i));
                for (int i : moved) if (!policy.allocateHostForVm(vms.get(i),dc.getHostList().get(next[i])))
                    throw new IllegalStateException("Migration resource allocation failed for VM " + i);
                for (int i : moved) if (next[i]!=p[i]) stats.migrations++;
                p=next;
            }
            dc.pulse(CloudSim.clock());
            double server=0,loss=0; double[] rackPower=new double[racks];
            load=Placement.loads(d,p,load.length);
            for (HostDynamicWorkload h : dc.<HostDynamicWorkload>getHostList()) {
                double actual=h.getUtilizationOfCpu();
                stats.cpuError=Math.max(stats.cpuError,Math.abs(actual-load[h.getId()]));
                boolean active=!h.getVmList().isEmpty(); double power=PowerModels.host(actual,active);
                server+=power; rackPower[h.getId()/(load.length/racks)]+=power;
                if (details!=null) details.printf(Locale.US,"%d,%d,%.12f,%.12f,%.9f,%d%n",
                        index*STEP,h.getId(),load[h.getId()],actual,power,h.getVmList().size());
            }
            for (double output:rackPower) loss+=ups.loss(output);
            int active=0,over=0;double rawMean=0,totalDemand=0;
            for (HostDynamicWorkload h:dc.<HostDynamicWorkload>getHostList()) if (!h.getVmList().isEmpty()) active++;
            for (double x:load) { if (x>.9+PowerModels.EPS) over++;totalDemand+=x; }
            for (int i=0;i<trace.length;i++) rawMean+=trace[i][index]/trace.length;
            if (stats.samples==0) stats.activeStart=active;
            stats.activeEnd=active;stats.activeMin=Math.min(stats.activeMin,active);stats.activeMax=Math.max(stats.activeMax,active);
            stats.activeSum+=active;stats.meanVmCpu+=rawMean;stats.meanPhysicalDemand+=totalDemand;stats.aboveThresholdHostSamples+=over;
            double[] theoretical=PowerModels.powers(d,p,load.length,racks,ups);
            stats.powerError=Math.max(stats.powerError,Math.abs(server+loss-theoretical[2]));
            stats.serverKwh+=server*STEP/3600000.; stats.upsKwh+=loss*STEP/3600000.; stats.samples++;
            if (times!=null) {
                times.printf(Locale.US,"%d,%.9f,%.9f,%.9f,%d",index*STEP,server,loss,server+loss,stats.migrations);
                times.printf(Locale.US,",%d,%d,%.9f,%.9f",active,over,rawMean,totalDemand);
                for (double output:rackPower) times.printf(Locale.US,",%.9f,%.9f",output,ups.loss(output));
                times.println();
            }
            index++; schedule(getId(),STEP,9100);
        }
    }
    public static Stats run(double[][] trace,int[] placement,int hostCount,int racks,PowerModels.Ups ups,
            String method,long seed,boolean dynamic,Path prefix) throws Exception {
        double[] mips=new double[trace.length];Arrays.fill(mips,MIPS);
        return run(trace,placement,hostCount,racks,ups,method,seed,dynamic,prefix,new Options(mips,false,true));
    }
    public static Stats run(double[][] trace,int[] placement,int hostCount,int racks,PowerModels.Ups ups,
            String method,long seed,boolean dynamic,Path prefix,Options options) throws Exception {
        if (options.vmMips.length!=trace.length) throw new IllegalArgumentException("Resource vector length mismatch");
        CloudSim.init(1,Calendar.getInstance(TimeZone.getTimeZone("UTC")),false); Log.disable();
        List<HostDynamicWorkload> hs=hosts(hostCount); Policy policy=new Policy(hs,placement);
        SupplyDatacenter dc=new SupplyDatacenter(hs,policy);
        DatacenterBroker broker=new DatacenterBroker("Broker");
        List<Vm> vms=new ArrayList<>(); List<Cloudlet> tasks=new ArrayList<>();
        for (int i=0;i<trace.length;i++) {
            Vm vm=new Vm(i,broker.getId(),options.vmMips[i],1,512,1000,1000,"Xen",new OnlineScheduler(options.vmMips[i]));
            vms.add(vm);
            Cloudlet c=new Cloudlet(i,1000000000000L,1,0,0,new Trace(trace[i]),new UtilizationModelNull(),new UtilizationModelNull());
            c.setUserId(broker.getId()); c.setVmId(i); tasks.add(c);
        }
        broker.submitVmList(vms); broker.submitCloudletList(tasks);
        Stats stats=new Stats();
        try (PrintWriter times=prefix==null?null:new PrintWriter(prefix+"_times.csv","UTF-8");
                PrintWriter details=prefix==null?null:new PrintWriter(prefix+"_hosts.csv","UTF-8")) {
            if (times!=null) {
                times.print("time_s,server_w,ups_loss_w,total_w,migrations,active_hosts,above_threshold_hosts,mean_vm_cpu,host_demand");
                for (int r=0;r<racks;r++) times.print(",rack"+r+"_output_w,rack"+r+"_loss_w");
                times.println();
            }
            if (details!=null) details.println("time_s,host_id,requested_cpu,allocated_cpu,power_w,vm_count");
            new Meter(dc,policy,vms,trace,racks,ups,method,seed,dynamic,times,details,stats,options);
            CloudSim.terminateSimulation(trace[0].length*STEP+ORIGIN+.01);
            CloudSim.startSimulation(); CloudSim.stopSimulation();
        }
        stats.created=broker.getVmsCreatedList().size();
        if (stats.created!=trace.length || stats.samples!=trace[0].length || stats.cpuError>1e-8 || stats.powerError>1e-5)
            throw new AssertionError("CloudSim verification failed: created="+stats.created+",samples="+stats.samples+",cpu="+stats.cpuError);
        if (prefix!=null) try (PrintWriter out=new PrintWriter(prefix+"_cloudlets.csv","UTF-8")) {
            out.println("cloudlet_id,vm_id,dc_id,exec_start,exec_finish,exec_time,status,completed_mi");
            for (Cloudlet c:tasks) out.printf(Locale.US,"%d,%d,%d,%.6f,%s,%s,%s,%d%n",c.getCloudletId(),c.getVmId(),
                    dc.getId(),c.getExecStartTime(),c.getCloudletStatus()==Cloudlet.SUCCESS?String.valueOf(c.getFinishTime()):"NA",
                    c.getCloudletStatus()==Cloudlet.SUCCESS?String.valueOf(c.getActualCPUTime()):"NA",c.getCloudletStatusString(),
                    ((OnlineScheduler)vms.get(c.getVmId()).getCloudletScheduler()).completedMi(c));
        }
        return stats;
    }
    public static void main(String[] args) throws Exception {
        Files.createDirectories(Paths.get("correction/results"));
        double[][] traces={{.4,.5},{.3,.4},{.2,.1}};
        Stats s=run(traces,new int[]{0,0,1},10,2,new PowerModels.Ups(2000,.0241,.0353,.0617,1),"BFD",101,false,
                Paths.get("correction/results/legacy_smoke"));
        System.out.println("PASS real CloudSim VMs="+s.created+" samples="+s.samples+" max_CPU_error="+s.cpuError);
    }
}
