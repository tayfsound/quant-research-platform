with open("services/orchestrator.py", "r") as f:
    lines = f.readlines()

# finalize satırını bul ve kaldır
finalize_idx = None
for i, line in enumerate(lines):
    if "ctx = self.engine.finalize(ctx)" in line:
        finalize_idx = i
        break

if finalize_idx is not None:
    finalize_line = lines.pop(finalize_idx)
    # Boş satır varsa kaldır
    if finalize_idx < len(lines) and lines[finalize_idx].strip() == "":
        lines.pop(finalize_idx)
    
    # self.memory.add satırını bul
    for j, line in enumerate(lines):
        if "self.memory.add({" in line:
            # if satırını bul (memory.add'dan önceki if)
            for k in range(j-1, -1, -1):
                if lines[k].strip().startswith("if ") and lines[k].strip().endswith(":"):
                    # finalize'ı if satırından önce ekle
                    lines.insert(k, "\n")
                    lines.insert(k, finalize_line)
                    break
            break

with open("services/orchestrator.py", "w") as f:
    f.writelines(lines)
print("✓ finalize moved before if block")
