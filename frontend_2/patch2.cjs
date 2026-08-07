const fs = require('fs');
let code = fs.readFileSync('src/routes/deals.$dealId.tsx', 'utf8');
code = code.replace(/React\.Children\.forEach\(tr\.props\.children/g, 'React.Children.forEach((tr.props as any).children');
fs.writeFileSync('src/routes/deals.$dealId.tsx', code);
