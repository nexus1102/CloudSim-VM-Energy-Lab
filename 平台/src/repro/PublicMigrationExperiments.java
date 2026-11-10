package repro;
import java.io.*;
import java.nio.file.*;
import java.util.*;

/** Isolates destination choice from the five initial placement policies; preserves historical CSVs. */
public final class PublicMigrationExperiments {
    private static final Path ROOT=Paths.get("paper_alignment/public_migration");
    private PublicMigrationExperiments(){}
    public static void main(String[] args) throws Exception {
        Files.createDirectories(ROOT.resolve("results"));PaperSettings base=new PaperSettings(Paths.get("paper_alignment/config/main.properties"));
        if(base.hosts!=100||base.racks!=5||base.step!=300)throw new IllegalArgumentException("Public comparison requires 100 Hosts / 5 racks / 300-second traces");
        int runs=0;
        try(PrintWriter out=new PrintWriter(ROOT.resolve("results/summary.csv").toFile(),"UTF-8")){
            out.println("prefix,case,controller,destination,method,day,seed,mean_vm_cpu,server_kwh,ups_kwh,total_kwh,started,finished,blocked,requested_mi,delivered_mi,migration_seconds,cpu_error,native_calls");
            for(String day:new String[]{"20110303","20110306","20110309"}){
                double[][] raw=Simulation.read(Paths.get("correction/inputs/cohort25_"+day+".csv"));
                if(raw.length!=100||raw[0].length!=288)throw new IllegalArgumentException("Expected 100 x 288 input "+day);
                double mean=0;for(double[] row:raw)for(double value:row)mean+=value/(raw.length*raw[0].length);
                for(String controller:new String[]{"threshold","framework_underload"})for(String destination:new String[]{"cloudsim_min_power","ups_min_power"}){
                    PaperSettings s=base.with("controller",controller).with("migration.destination",destination)
                            .with("online.source","Public destination finder on detached snapshots; author online policy not established");
                    for(String method:PaperPlacement.METHODS)for(int k=0;k<(day.equals("20110303")?5:1);k++){
                        long seed=101+101*k;String id=controller+"_"+destination+"_"+method+"_"+day+"_"+seed;
                        long before=PublicMigrationDestination.nativeCalls;
                        PowerSupplyAwareDataCenter dc=PaperRun.run(raw,s,method,seed,null,ROOT.resolve("results/"+id),day.equals("20110303")&&k==0);
                        long calls=PublicMigrationDestination.nativeCalls-before;
                        out.printf(Locale.US,"%s,%s,%s,%s,%s,%s,%d,%.12f,%.9f,%.9f,%.9f,%d,%d,%d,%.9f,%.9f,%.9f,%.9f,%d%n",
                                id,"cohort25_"+day,controller,destination,method,day,seed,mean,dc.serverJ/3600000,dc.upsJ/3600000,dc.kwh(),
                                dc.starts,dc.finishes,dc.blocked,dc.requestedMI,dc.deliveredMI,dc.migrationSeconds,dc.cpuCheckError,calls);
                        out.flush();if(out.checkError())throw new IOException("Public comparison summary write failed");runs++;
                        System.out.printf(Locale.US,"public %d/140 %s %.3fkWh migrations=%d nativeCalls=%d%n",runs,id,dc.kwh(),dc.starts,calls);
                    }
                }
            }
        }
        if(runs!=140)throw new IllegalStateException("Incomplete public destination experiment count "+runs);
        System.out.println("PASS 140 public destination comparisons; previous paper results unchanged");
    }
}
