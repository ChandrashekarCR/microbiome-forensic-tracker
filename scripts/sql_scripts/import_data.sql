-- Set SQLite to csv mode
.mode csv

-- Delete table if it alread existis
DROP TABLE IF EXISTS malmo_phylum;
DROP TABLE IF EXISTS malmo_class;
DROP TABLE IF EXISTS malmo_order;
DROP TABLE IF EXISTS malmo_family;
DROP TABLE IF EXISTS malmo_genus;
DROP TABLE IF EXISTS malmo_species;

-- Import each CSV into malmo_* table
-- Navigate to the place where the data is stored and then run the script
.import kraken_bracken_phylum.csv malmo_phylum
.import kraken_bracken_class.csv malmo_class
.import kraken_bracken_order.csv malmo_order
.import kraken_bracken_family.csv malmo_family
.import kraken_bracken_genus.csv malmo_genus
.import kraken_bracken_species.csv malmo_species


/*
Run this command from where the directory where the csv files are stored

ls
kraken_bracken_class.csv  kraken_bracken_family.csv  kraken_bracken_genus.csv  kraken_bracken_order.csv  kraken_bracken_phylum.csv  kraken_bracken_species.csv
kraken_bracken_class.log  kraken_bracken_family.log  kraken_bracken_genus.log  kraken_bracken_order.log  kraken_bracken_phylum.log  kraken_bracken_species.log

pwd
<some path here>/11_final_reports

sqlite3 ~/binp51/databases/malmo.db < ~/binp51/scripts/sql_scripts/import_data.sql 
*/