"""Build a sample statement so the tool can be run end to end with no mailbox."""
import csv, random
from pathlib import Path
here = Path(__file__).parent
rows = [["Datum","Naam / Omschrijving","Rekening","Tegenrekening","Code","Af Bij","Bedrag (EUR)","MutatieSoort","Mededelingen"]]
data = [
 ("20260318","Acme Supplies BV","NL13TEST0123456789","NL69TEST0000000001","GT","Af","121,00","Online bankieren","Naam: Acme Supplies BV Omschrijving: factuur INV-2026/0042"),
 ("20260405","Vodafone Espana SLU","NL13TEST0123456789","ES2800000000000000000002","GT","Af","49,95","Incasso","Naam: VODAFONE ES Omschrijving: F-2026-118 abono movil"),
 ("20260412","Gestoria Marina Alta","NL13TEST0123456789","ES9800000000000000000003","GT","Af","302,50","Online bankieren","Omschrijving: honorarios marzo"),
 ("20260420","J. Tenant","NL13TEST0123456789","NL85TEST0000000004","GT","Bij","825,00","Online bankieren","Omschrijving: Rent April 2026"),
 ("20260422","SUPERMARKT 1234","NL13TEST0123456789","","BA","Af","63,21","Betaalautomaat","Pasvolgnr 003 22-04-2026 boodschappen"),
]
rows.extend(data)
with open(here/'sample-statement.csv','w',newline='',encoding='utf-8') as f:
    csv.writer(f, quoting=csv.QUOTE_ALL).writerows(rows)
print('wrote', here/'sample-statement.csv')
