import os
with open(r'c:\Users\MrHarshGurjar\Desktop\code\Credit_Dossier\frontend\src\routes\deals.$dealId.tsx', 'r', encoding='utf8') as f:
    lines = f.readlines()

for idx in range(650, 970):
    print(f"{idx+1}: {lines[idx].strip()}")
