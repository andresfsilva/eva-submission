# Submission automation


These scripts are meant to be used by EVA helpdesk personnel to manage submissions to the EVA.
They process the submission in a semi-automated way and record the outcome of each step in a yaml file located in a given submission directory


## Scripts


### Information about a submission

The following script simply surveys the content of FTP boxes and returns a short text that should provide enough information to create the submission ticket.

```bash
python detect_submission.py --ftp_box 3 --submitter john
```

### Copy relevant file to the submission folder

This script can be used to grab the relevant files from the ftp_box and to copy them to the submission folder when you supply `--ftp_box` and `--submitter` parameters. 
It will also prepare the submission folder and create the directory structure  and the config file required for the rest of the execution.
Without the above parameters, it only prepares the submission folder.


```bash
python prepare_submission.py --ftp_box 3 --submitter john --eload 677
```

or 

```bash
python prepare_submission.py --eload 677
```

### Validate the submitted data

This script will run the validation required to ensure that the data is suitable to be archived. It will check
 - The metadata spreadsheet format (metadata_check) 
 - The sample names in the VCF and metadata matches (sample_check)
 - The VCF conforms to the [submission standards](https://www.ebi.ac.uk/eva/?Help#submissionPanel) (vcf_check)
 - The VCF reference allele match the reference genome. (assembly_check)

 At the end of the run if all the validation pass the script will register the input vcf and metadata as valid in the config file.
 
 ```bash
python validate_submission.py --eload 677
```

This command will output a report to standard output to detail the validation results.

You can run only part of the validation by specifying the validation task
```bash
python validate_submission.py --eload 677 --validation_tasks metadata_check
```
The valid values for the validation tasks are: `metadata_check`, `sample_check`, `vcf_check`, and `assembly_check`

You can also force a validation to pass by specifying the flag `--set_as_valid`. This will mark all validation tasks performed as Forced.


### Brokering to BioSamples and ENA

Once the validation pass and VCF files and metadata are marked as valid, the brokering can start. It will:
 - Index the VCF file(s) and calculate their md5
 - Create BioSamples entries in BioSamples
 - Upload the VCF files to ENA
 - Create and upload ENA XML files
 - Parse and store the submission, project and analysis accession

 ```bash
python broker_submission.py --eload 677
```

You can specify a list of VCF and/or a metadata file on the command line to override the one set in the config file by the validation step.

 ```bash
python broker_submission.py --eload 677 --vcf_files /path/to/vcf1.vcf /path/to/vcf2.vcf --metadata_file /path/to/metadata.xlsx
```

### Data ingestion

After validation and brokering are done, the data can be loaded into our databases and made publicly available.
This involves three main steps:

1. Loading submission metadata from ENA into EVAPRO (`metadata_load`)
2. Accessioning VCF files (`accession`)
3. Loading into the variant warehouse (`variant_load`)

By default, the script will run all of these tasks, though you may specify a subset using the flag `--tasks`.
Note that as some steps are long-running the script is best run in a screen/tmux session.

```bash
# To run everything
python ingest_submission.py --eload 765 --instance 1 --vep_version 89 --vep_cache_version 89 --aggregation NONE

# Only accessioning - VEP versions not needed
python ingest_submission.py --eload 765 --instance 1 --aggregation NONE --tasks accession

# Only variant load - accession instance id not needed
python ingest_submission.py --eload 765 --vep_version 89 --vep_cache_version 89 --aggregation NONE --tasks variant_load
```

### Backlog automation

Older studies that have been manually brokered will need to have a preparation script run before ingestion automation.
This will create the config file and run validation on the VCF files (without metadata validation) to ensure they are up to current standards.

```bash
python prepare_backlog_study.py --eload 506
```

If the files are valid then ingestion can be run as usual.
