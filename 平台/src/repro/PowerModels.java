package repro;

/** Equations (2-1)--(2-4), (2-10)--(2-17), all power units W. */
public final class PowerModels {
    public static final double IDLE = 218.3, MAX = 350, EPS = 1e-8;
    private PowerModels() { }
    public static double host(double utilization, boolean awake) {
        if (!Double.isFinite(utilization) || utilization < -EPS || utilization > 1 + EPS)
            throw new IllegalArgumentException("Host CPU outside [0,1]: " + utilization);
        if (!awake) {
            if (utilization > EPS) throw new IllegalArgumentException("Sleeping host has CPU demand");
            return 0;
        }
        return IDLE + (MAX - IDLE) * Math.max(0, Math.min(1, utilization));
    }
    public static final class Ups {
        public final double rated, a0, a1, a2, factor;
        public Ups(double rated, double a0, double a1, double a2, double factor) {
            if (!(rated > 0 && factor >= 1 && a0 >= 0 && a1 >= 0 && a2 >= 0)
                    || !Double.isFinite(rated + a0 + a1 + a2 + factor))
                throw new IllegalArgumentException("Invalid UPS coefficients or capacity");
            this.rated = rated; this.a0 = a0; this.a1 = a1; this.a2 = a2; this.factor = factor;
        }
        public double loss(double output) {
            // (2-17) uses usable capacity, not total redundant nameplate capacity.
            if (!Double.isFinite(output) || output < -EPS || output > rated + EPS)
                throw new IllegalArgumentException("UPS output outside usable capacity: " + output);
            double installed = rated * factor, x = Math.max(0, output) / installed;
            return installed * (a0 * x * x + a1 * x + a2);
        }
        public double efficiency(double output) { return output / (output + loss(output)); }
        public double input(double output) { return output + loss(output); }
    }
    public static Ups model(String architecture) {
        boolean dc = architecture.contains("DC"), twoN = architecture.startsWith("2N");
        return new Ups(7000, dc ? .0549 : .0376, dc ? .0077 : .0069,
                dc ? .0207 : .0319, twoN ? 2 : 1.25);
    }
    public static double[] powers(double[] demand, int[] placement, int hosts, int racks, Ups ups) {
        double[] utilization = new double[hosts], rack = new double[racks];
        boolean[] awake = new boolean[hosts];
        if (placement.length != demand.length || hosts % racks != 0)
            throw new IllegalArgumentException("Invalid placement dimensions");
        for (int i = 0; i < demand.length; i++) {
            if (placement[i] < 0 || placement[i] >= hosts) throw new IllegalArgumentException("VM missing or host out of range");
            if (!Double.isFinite(demand[i]) || demand[i] < 0) throw new IllegalArgumentException("Invalid CPU demand");
            utilization[placement[i]] += demand[i]; awake[placement[i]] = true;
        }
        double server = 0, loss = 0;
        for (int h = 0; h < hosts; h++) {
            double p = host(utilization[h], awake[h]); server += p;
            rack[h / (hosts / racks)] += p;
        }
        for (double p : rack) loss += ups.loss(p); // UPS remains energized at zero rack load.
        return new double[]{server, loss, server + loss};
    }
    public static void close(double a, double b) {
        if (Math.abs(a - b) > 1e-7) throw new AssertionError(a + " != " + b);
    }
    public static void main(String[] args) {
        close(host(0, true), 218.3); close(host(1, true), 350); close(host(0, false), 0);
        Ups literal = new Ups(2000, .0241, .0353, .0617, 1);
        close(literal.loss(0), 123.4); close(literal.loss(900), 164.9305);
        close(literal.input(900), 900 / literal.efficiency(900));
        Ups swapped = new Ups(2000, .0617, .0353, .0241, 1);
        close(swapped.loss(900), 104.9585);
        for (String s : new String[]{"N+1AC", "N+1DC", "2NAC", "2NDC"}) {
            Ups u = model(s); close(u.input(0), u.rated * u.factor * u.a2);
            close(u.input(7000), 7000 / u.efficiency(7000));
        }
        try { host(1.1, true); throw new AssertionError("Overload accepted"); }
        catch (IllegalArgumentException expected) { }
        System.out.println("PASS power equations, zero-load limit, capacity and redundant supply");
    }
}
