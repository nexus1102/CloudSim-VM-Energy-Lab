package repro;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Behavioral baseline captured before extraction; elapsed time deliberately excluded. */
public final class PlacementRegression {
    public static void main(String[] args) throws Exception {
        if (args.length != 2 || !(args[0].equals("--capture") || args[0].equals("--verify")))
            throw new IllegalArgumentException("--capture|--verify baseline.csv");
        Path target = Paths.get(args[1]);
        if (args[0].equals("--capture") && Files.exists(target))
            throw new IllegalArgumentException("Never overwrite a regression baseline: " + target);
        List<String> actual = new ArrayList<>();
        actual.add("level,initialization,operators,rack_operators,method,seed,behavior_sha256");
        ResearchConfig base = new ResearchConfig(Paths.get("research_platform/config/default.properties"));
        for (int level : new int[]{10,30,70}) {
            double[][] raw = Simulation.read(Paths.get("correction/inputs/static_" + level + ".csv"));
            double[] demand = new double[raw.length];
            for (int i=0;i<demand.length;i++) demand[i]=raw[i][0]*base.settings.vmMips(i)/base.settings.hostMips;
            for (String init : new String[]{"random_hosts","feasible_packing"})
                for (String op : new String[]{"legacy","aligned_feasible"})
                    for (String rack : new String[]{"legacy","aligned_gene"})
                        for (String method : ResearchPlacement.METHODS) for (long seed : new long[]{101,202}) {
                            ResearchConfig c=base.with("research.initialization",init)
                                .with("research.genetic.operators",op).with("research.rack.operators",rack)
                                .with("research.trace.placements","true");
                            ResearchPlacement.Answer a=ResearchPlacement.solve(method,demand,100,5,
                                new SupplyPowerModel(c.settings),seed,8,.9,false);
                            String behavior=Arrays.toString(a.host)+Arrays.toString(a.history)+Arrays.deepToString(a.mappingHistory);
                            byte[] hash=MessageDigest.getInstance("SHA-256").digest(behavior.getBytes(StandardCharsets.UTF_8));
                            StringBuilder hex=new StringBuilder();for(byte b:hash)hex.append(String.format("%02x",b&255));
                            actual.add(level+","+init+","+op+","+rack+","+method+","+seed+","+hex);
                        }
        }
        if (args[0].equals("--capture")) Files.write(target,actual,StandardCharsets.UTF_8);
        else if (!actual.equals(Files.readAllLines(target,StandardCharsets.UTF_8)))
            throw new AssertionError("Placement behavior changed; inspect mappings/history against " + target);
        System.out.println("PASS " + (actual.size()-1) + " placement mappings and complete histories (" + args[0] + ")");
    }
}
