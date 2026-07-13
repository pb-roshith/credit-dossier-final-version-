const fs = require('fs');
const code = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8').split('\n');
let divOpens = 0, divCloses = 0;

for (let i = 466; i <= 966; i++) {
  const line = code[i] || '';
  const opens = (line.match(/<div(\s|>)/g) || []).length;
  const closes = (line.match(/<\/div>/g) || []).length;
  divOpens += opens;
  divCloses += closes;
}
console.log('divOpens:', divOpens, 'divCloses:', divCloses);
