const fs = require('fs');
const code = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8').split('\n');

let balance = 0;
for (let i = 466; i <= 970; i++) {
  const line = code[i] || '';
  
  // match <div ...> but NOT <div ... />
  // actually in JSX divs are rarely self-closing, but we can handle it
  const opens = (line.match(/<div(\s|>)/g) || []).length;
  
  // check for self-closing divs just in case
  const selfCloses = (line.match(/<div[^>]*\/>/g) || []).length;
  
  const closes = (line.match(/<\/div>/g) || []).length;
  
  balance += (opens - selfCloses - closes);
  
  if (balance <= 0 && opens - selfCloses - closes !== 0) {
    console.log(`Line ${i+1}: Balance became ${balance}. Line content: ${line.trim()}`);
  }
}
