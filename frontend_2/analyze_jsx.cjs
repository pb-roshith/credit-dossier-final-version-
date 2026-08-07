const fs = require('fs');
const code = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8');

// I will write a simple stack parser to find the unmatched JSX tag.
let stack = [];
let lines = code.split('\n');

for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  
  // Very rough heuristic for JSX tags in this file to find what's missing
  let match;
  let regex = /<(\w+)([^>]*)>|<\/(\w+)>/g;
  while ((match = regex.exec(line)) !== null) {
    if (match[0].includes('/>')) continue;
    if (match[3]) {
      // Closing tag
      if (stack.length > 0 && stack[stack.length - 1].tag === match[3]) {
        stack.pop();
      } else {
        console.log('Mismatched closing tag:', match[3], 'at line', i+1);
      }
    } else if (match[1]) {
      // Opening tag
      stack.push({tag: match[1], line: i+1});
    }
  }
}

if (stack.length > 0) {
  console.log('Unclosed tags:', stack.slice(-5));
} else {
  console.log('No unclosed tags detected by heuristic.');
}
