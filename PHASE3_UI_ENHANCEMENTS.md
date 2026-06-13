# Phase 3: UI/UX Enhancements - Implementation Plan

## What Needs To Be Added to index.html

### 1. Dark Mode Support
```javascript
// Add to Vue setup()
const darkMode = ref(false);
const toggleDarkMode = () => {
  darkMode.value = !darkMode.value;
  localStorage.setItem('darkMode', darkMode.value);
  document.documentElement.classList.toggle('dark', darkMode.value);
};

// Load on mount
onMounted(() => {
  const saved = localStorage.getItem('darkMode') === 'true';
  darkMode.value = saved;
  if (saved) document.documentElement.classList.add('dark');
});
```

### 2. Column Mapping UI State
```javascript
// Add to reactive state
const uploadState = reactive({
  step: 1, // 1=select file, 2=preview & map, 3=importing
  preview: { headers: [], sample_rows: [], filepath: '', filename: '' },
  columnMapping: {},
  systemFields: ['company_name', 'website', 'industry', 'location', 'app_status', 
                 'contact_email', 'whatsapp_number', 'linkedin', 'subject', 'pitch']
});
```

### 3. Enhanced File Upload Flow
**Step 1: File Selection** (existing)
**Step 2: Preview & Column Mapping**
```html
<div v-if="uploadState.step === 2" class="space-y-6">
  <h3>Map Your Columns</h3>
  <table>
    <thead>
      <tr><th>Your File Column</th><th>Maps To</th><th>Sample Data</th></tr>
    </thead>
    <tbody>
      <tr v-for="(header, idx) in uploadState.preview.headers" :key="idx">
        <td>{{ header }}</td>
        <td>
          <select v-model="uploadState.columnMapping[idx]">
            <option value="">-- Skip --</option>
            <option v-for="field in uploadState.systemFields" :key="field" :value="field">
              {{ field }}
            </option>
          </select>
        </td>
        <td>{{ uploadState.preview.sample_rows[0]?.[idx] || 'N/A' }}</td>
      </tr>
    </tbody>
  </table>
  <button @click="proceedWithImport">Import {{ uploadState.preview.sample_rows.length }} rows</button>
</div>
```

**Step 3: Importing with progress**
```html
<div v-if="uploadState.step === 3" class="text-center">
  <div class="loader"></div>
  <p>Importing leads... Detecting duplicates...</p>
</div>
```

### 4. Updated handleFileUpload Function
```javascript
const handleFileUpload = async () => {
  if (!selectedFile.value) return;
  isUploading.value = true;
  const formData = new FormData();
  formData.append('file', selectedFile.value);
  formData.append('preview', 'true'); // Request preview mode

  try {
    const res = await fetch('/api/leads/upload', { method: 'POST', body: formData });
    const data = await res.json();
    isUploading.value = false;
    
    if (data.success && data.preview) {
      // Show preview & mapping
      uploadState.step = 2;
      uploadState.preview = data;
      
      // Auto-detect mappings
      data.headers.forEach((header, idx) => {
        const lower = header.toLowerCase();
        if (lower.includes('company') || lower.includes('business')) uploadState.columnMapping[idx] = 'company_name';
        else if (lower.includes('email')) uploadState.columnMapping[idx] = 'contact_email';
        else if (lower.includes('website')) uploadState.columnMapping[idx] = 'website';
        // ... more auto-detection
      });
    } else {
      showToast(data.message, 'error');
    }
  } catch (e) {
    isUploading.value = false;
    showToast('Error uploading file.', 'error');
  }
};

const proceedWithImport = async () => {
  uploadState.step = 3;
  const formData = new FormData();
  // Use cached filepath from preview
  formData.append('filepath', uploadState.preview.filepath);
  formData.append('column_mapping', JSON.stringify(uploadState.columnMapping));
  formData.append('preview', 'false'); // Full import now

  try {
    const res = await fetch('/api/leads/upload', { method: 'POST', body: formData });
    const data = await res.json();
    
    if (data.success) {
      showUploadModal.value = false;
      uploadState.step = 1;
      showToast(`${data.imported} leads imported. ${data.duplicates} duplicates skipped.`, 'success');
      fetchLeads();
      fetchStats();
    } else {
      showToast(data.message, 'error');
    }
  } catch (e) {
    showToast('Import failed.', 'error');
  }
};
```

### 5. Loading Spinner CSS
```css
@keyframes spin {
  to { transform: rotate(360deg); }
}
.loader {
  border: 4px solid #f3f4f6;
  border-top: 4px solid #3b82f6;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 1s linear infinite;
  margin: 0 auto;
}
```

### 6. Dark Mode Tailwind Classes
Add `dark:` variants to existing classes:
```html
<body class="bg-slate-50 dark:bg-slate-900">
<div class="bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100">
```

### 7. Dark Mode Toggle Button (in header)
```html
<button @click="toggleDarkMode" class="p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-700">
  <svg v-if="!darkMode" class="w-5 h-5"><!-- Moon icon --></svg>
  <svg v-else class="w-5 h-5"><!-- Sun icon --></svg>
</button>
```

## Implementation Strategy

**Option A: Full File Replace** - Replace entire index.html with enhanced version (risky, may break things)
**Option B: Incremental Enhancement** - Add JavaScript enhancements only, keep existing HTML structure
**Option C: Separate Component File** - Create `upload_wizard.html` and inject via Vue component

## Recommended: Option B
- Minimal risk
- Keeps existing functionality
- Adds features progressively

Would you like me to implement Option B with the upload wizard enhancement?
