const fs = require('fs');
const lines = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8').split('\n');
for (let i = 466; i >= 0; i--) {
  if (lines[i].includes('function') || lines[i].includes('=> {') || lines[i].includes('={')) {
    console.log(`Line ${i+1}: ${lines[i]}`);
  }
}
