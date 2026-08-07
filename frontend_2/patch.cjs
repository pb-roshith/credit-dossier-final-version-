const fs = require('fs');
let lines = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8').split('\n');

if (lines[571].includes('</div>')) {
  lines.splice(571, 1);
  console.log('Removed line 572');
}

let endLine = -1;
for (let i = 900; i < lines.length; i++) {
  if (lines[i].includes('/* ── Accuracy Panel Component')) {
    endLine = i;
    break;
  }
}

if (endLine !== -1) {
  let insertIdx = endLine - 1;
  while(lines[insertIdx].trim() === '') insertIdx--;
  
  if (lines[insertIdx].includes('}') && lines[insertIdx-1].includes(');')) {
    lines.splice(insertIdx-1, 0, '        </div>', '      </div>', '    </div>');
    console.log('Inserted 3 </div> tags');
  }
}

fs.writeFileSync('src/routes/deals.$dealId.tsx', lines.join('\n'));
