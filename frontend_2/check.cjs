const fs = require('fs');
const babel = require('@babel/parser');

const code = fs.readFileSync(require('path').resolve(__dirname, 'src/routes/deals.$dealId.tsx'), 'utf8');

try {
  babel.parse(code, {
    sourceType: 'module',
    plugins: ['jsx', 'typescript']
  });
  console.log('Parse successful!');
} catch (e) {
  console.log('Error at line:', e.loc?.line, 'col:', e.loc?.column);
  console.log(e.message);
  
  if (e.loc) {
    const lines = code.split('\n');
    for (let i = Math.max(0, e.loc.line - 15); i < Math.min(lines.length, e.loc.line + 5); i++) {
      console.log(`${i + 1}: ${lines[i]}`);
      if (i + 1 === e.loc.line) {
        console.log(' '.repeat(e.loc.column + String(i + 1).length + 2) + '^');
      }
    }
  }
}
