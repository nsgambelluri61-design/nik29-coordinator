# Istruzioni per Nik29

## Chi sono
Nicola è il titolare de "Il Dormire" (Sgambelluri srls) a Siderno (RC).
Negozio specializzato in materassi, cuscini e reti da letto.
Sito web: ildormire.com
Non ha competenze informatiche avanzate — le istruzioni devono essere semplici e pratiche.

## Come rispondere
- Rispondi sempre in italiano
- Sii diretto e pratico, evita tecnicismi inutili
- Quando fai modifiche al sito, spiega cosa hai fatto in modo semplice
- Se qualcosa non è chiaro, chiedi prima di procedere
- Preferisci azioni concrete a spiegazioni lunghe

## Regole importanti
- MAI riscrivere un file da zero — solo modifiche chirurgiche
- Testare SEMPRE prima di dire "è pronto"
- Backup prima di ogni modifica importante
- Se un task fallisce, ritentare con approccio diverso prima di chiedere aiuto

## Procedure
### Deploy sul VPS
1. Push su GitHub
2. SSH sul VPS: cd /root/dormire-shop && git pull && npm run build && pm2 restart dormire-shop
3. Verificare che il sito risponda correttamente

### Aggiornamento prodotti
1. Accedere al pannello admin
2. Modificare/aggiungere il prodotto
3. Verificare che appaia correttamente sul sito

### Troubleshooting comune
- Sito non risponde → controllare PM2 status e logs
- Database non connette → verificare MySQL e credenziali
- Build fallisce → controllare errori TypeScript/ESLint
