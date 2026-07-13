const fs = require('fs');
const code = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8').split('\n');

let balance = 0;
// NarrativesTab return starts at 466
for (let i = 466; i <= 966; i++) {
  const line = code[i] || '';
  const opens = (line.match(/<div(\s|>)/g) || []).length;
  const closes = (line.match(/<\/div>/g) || []).length;
  const selfCloses = (line.match(/<div[^>]*\/>/g) || []).length;
  balance += (opens - closes - selfCloses);
  
  if (closes > opens) {
    console.log(`Line ${i+1} closes more than it opens. Balance: ${balance}`);
  }
}
console.log(`Final balance at end: ${balance}`);
