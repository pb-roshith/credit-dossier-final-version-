const fs = require('fs');
const code = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8');

const { parse } = require('@babel/parser');
const traverse = require('@babel/traverse').default;

try {
  parse(code, {
    sourceType: 'module',
    plugins: ['jsx', 'typescript']
  });
  console.log("Successfully parsed!");
} catch (e) {
  console.log("Error:", e.message);
}
