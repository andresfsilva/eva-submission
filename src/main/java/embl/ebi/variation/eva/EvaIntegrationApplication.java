package embl.ebi.variation.eva;

import embl.ebi.variation.eva.seqrep_fasta_dl.ENASequenceReportDownload;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.GenericMessage;

import java.io.File;
import java.io.IOException;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

@SpringBootApplication
@IntegrationComponentScan
@EnableAutoConfiguration
public class EvaIntegrationApplication {


	public static void main(String[] args) {

        ConfigurableApplicationContext ctx = SpringApplication.run(EvaIntegrationApplication.class, args);

        String assemblyAccession = "GCA_000001405.10";
        String localAssemblyDirectoryRoot = "/home/tom/Job_Working_Directory/Java/eva-integration/src/main/resources/test_dl/ftpInbound";
        String sequenceReportFile = Paths.get(localAssemblyDirectoryRoot, assemblyAccession + "_sequence_report.txt").toString();

        String fastaFile = "/home/tom/Job_Working_Directory/Java/eva-integration/src/main/resources/test_dl/ftpInbound/GCA_000001405.10.fasta2";

//        setupEnvironment(ctx, assemblyAccession);

        GenericMessage message = new GenericMessage<String>(sequenceReportFile);

        if (!new File(sequenceReportFile).exists()){
            MessageChannel inputChannel = ctx.getBean("inputChannel", MessageChannel.class);
            inputChannel.send(message);
        } else if (!new File(fastaFile).exists()){
            MessageChannel channelIntoDownloadFasta = ctx.getBean("channelIntoDownloadFasta", MessageChannel.class);
            channelIntoDownloadFasta.send(message);
        }

//        ctx.close();
	}
}
