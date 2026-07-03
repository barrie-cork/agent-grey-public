# PRISMA Diagram Developer Guide

## Overview

This guide explains how to modify and maintain the PRISMA 2020 "Other Methods" flow diagram implementation in Agent Grey. The diagram is rendered using HTML Canvas via JavaScript and complies with the official [PRISMA 2020 guidelines](https://www.prisma-statement.org/prisma-2020-flow-diagram).

## Architecture

### Technology Stack
- **Frontend**: HTML5 Canvas API with JavaScript
- **Framework**: Vanilla JavaScript (no dependencies)
- **Export**: PNG and PDF (via jsPDF)
- **Data Source**: Django backend (`PrismaReportingService`)

### File Locations

```
agent-grey-core-requirements/
├── apps/
│   └── reporting/
│       ├── static/reporting/js/
│       │   └── prisma2020.js                    # Main diagram renderer
│       ├── templates/reporting/exports/
│       │   └── prisma_other_methods.html        # Django template (HTML/CSS)
│       └── services/
│           └── prisma_reporting_service.py      # Data service
├── tests/
│   └── prisma-other-methods-test.html           # Standalone test file
└── docs/
    └── features/UI/
        └── PRISMA_DIAGRAM_DEVELOPER_GUIDE.md    # This file
```

## Diagram Structure

The PRISMA "Other Methods" diagram consists of:

```
┌─────────────────────────────────────────┐
│ Header: "Identification of studies      │ [Yellow/orange]
│         via other methods"               │
└─────────────────────────────────────────┘
              │
              ▼
    ┌───────────────────┐
    │ Records identified │ [Left-aligned]
    │ from: sources      │
    └───────────────────┘
              │
              ▼
    ┌──────────────┐ ──────→ ┌─────────────────┐
    │ Reports      │          │ Reports not     │ [Grey]
    │ sought       │          │ retrieved       │
    └──────────────┘          └─────────────────┘
              │
              ▼
    ┌──────────────┐ ──────→ ┌─────────────────┐
    │ Reports      │          │ Reports         │ [Grey]
    │ assessed     │          │ excluded        │
    └──────────────┘          └─────────────────┘
              │
              ▼
    ┌──────────────┐
    │ Reports      │ [Left-aligned]
    │ included     │
    └──────────────┘
```

## Key Components

### 1. PRISMA2020Diagram Class

Located in: `apps/reporting/static/reporting/js/prisma2020.js`

**Constructor Parameters:**
```javascript
const diagram = new PRISMA2020Diagram('canvas-id');
```

**Main Methods:**
```javascript
// Draw complete diagram
diagram.draw(data);

// Export as PNG
diagram.export_as_png('filename.png');

// Export as PDF
diagram.export_as_pdf('filename.pdf');
```

### 2. Layout Constants

```javascript
// In constructor
this.padding = 40;              // Canvas padding
this.box_width = 220;           // Standard box width
this.box_height = 80;           // Standard box height
this.arrow_size = 6;            // Arrow head size
this.vertical_spacing = 25;     // Space between vertical stages
```

### 3. Colour Scheme

```javascript
this.colors = {
    header: '#ffc107',          // Yellow/orange header
    main_box: '#ffffff',        // White boxes
    excluded_box: '#ffffff',    // White (not grey as in HTML version)
    included_box: '#ffffff',    // White
    text: '#000000',            // Black text
    border: '#000000',          // Black borders
    arrow: '#000000'            // Black arrows
};
```

## Modifying the Diagram

### Adding a New Box

1. **Create a drawing method:**
```javascript
draw_new_box(start_y, data) {
    const box_spacing = 40;
    const total_width = (this.box_width * 2) + box_spacing;
    const left_x = (this.canvas.width - total_width) / 2;

    // Draw the box
    this.draw_box(left_x, start_y, this.box_width, this.box_height,
                  this.colors.main_box);

    // Add text
    this.ctx.font = `${this.font_size}px Arial`;
    this.ctx.fillStyle = this.colors.text;
    this.ctx.textAlign = 'center';

    const center_x = left_x + this.box_width / 2;
    this.ctx.fillText('New Box Label', center_x, start_y + 30);
    this.ctx.fillText(`(n = ${data.count || 0})`, center_x, start_y + 45);

    // Return position for next box
    return start_y + this.box_height + this.vertical_spacing;
}
```

2. **Call it in the main `draw()` method:**
```javascript
draw(data) {
    // ... existing code ...

    const new_box_y = this.draw_new_box(previous_y, data.new_section);

    // Continue with next boxes
}
```

### Changing Box Alignment

**Centre-aligned box:**
```javascript
const x = (this.canvas.width - this.box_width) / 2;
```

**Left-aligned box:**
```javascript
const box_spacing = 40;
const total_width = (this.box_width * 2) + box_spacing;
const left_x = (this.canvas.width - total_width) / 2;
```

**Right-aligned box:**
```javascript
const box_spacing = 40;
const total_width = (this.box_width * 2) + box_spacing;
const right_x = (this.canvas.width + total_width) / 2 - this.box_width;
```

### Modifying Arrows

**Vertical arrow (box to box):**
```javascript
// From bottom of box to top of next box
const arrow_start_y = box_y + this.box_height;
const arrow_end_y = arrow_start_y + this.vertical_spacing;
this.draw_arrow(center_x, arrow_start_y, center_x, arrow_end_y);
```

**Horizontal arrow (box to box):**
```javascript
// From right edge of left box to left edge of right box
this.draw_arrow(
    left_x + this.box_width,           // From right edge
    start_y + this.box_height / 2,     // Middle of box height
    right_x,                            // To left edge
    start_y + this.box_height / 2      // Same height
);
```

**Angled arrow:**
```javascript
// Arrow automatically calculates angle
this.draw_arrow(from_x, from_y, to_x, to_y);
```

### Changing Text Formatting

**Bold text:**
```javascript
this.ctx.font = `bold ${this.font_size}px Arial`;
```

**Different font size:**
```javascript
this.ctx.font = `9px Arial`;  // Smaller text for details
```

**Text alignment:**
```javascript
this.ctx.textAlign = 'center';  // or 'left', 'right'
```

**Multi-line text:**
```javascript
this.ctx.fillText('Line 1', x, y);
this.ctx.fillText('Line 2', x, y + 14);  // 14px line height
this.ctx.fillText('Line 3', x, y + 28);
```

### Adjusting Spacing

**Vertical spacing between stages:**
```javascript
this.vertical_spacing = 25;  // Increase for more space
```

**Horizontal spacing between columns:**
```javascript
const box_spacing = 40;      // Increase for wider gap
```

**Canvas size:**
```javascript
this.canvas.width = 600;     // Total width
this.canvas.height = 800;    // Total height
```

## Data Structure

The diagram expects data in this format:

```javascript
const data = {
    identification: {
        websites: 120,
        organizations: 45,
        citation_searching: 35
    },
    retrieval: {
        reports_sought: 180,
        reports_retrieved: 150,
        reports_not_retrieved: 30
    },
    eligibility: {
        reports_assessed: 150,
        excluded: 120,
        exclusion_reasons: {
            'Reason 1': 45,
            'Reason 2': 35,
            'Reason 3': 40
        }
    },
    included: {
        total: 30,
        reports_included: 30
    }
};
```

## Testing Changes

### 1. Quick Browser Test

Open the standalone test file:
```bash
# Navigate to tests directory
cd tests/

# Open in browser (Linux/WSL)
xdg-open prisma-other-methods-test.html

# Or use file:// URL
file:///mnt/d/Python/.../tests/prisma-other-methods-test.html
```

### 2. Modify Test Data

Edit `prisma-other-methods-test.html` and update the test data:

```javascript
const testData = {
    identification: {
        websites: 200,  // Change values here
        organizations: 80,
        citation_searching: 50,
        total: 330
    },
    // ... rest of data
};
```

### 3. Django Integration Test

```python
# In Django shell
from apps.reporting.services.prisma_reporting_service import PrismaReportingService

service = PrismaReportingService()
data = service.generate_prisma_flow_data(session_id)

# Check data structure
print(data['identification'])
print(data['retrieval'])
print(data['eligibility'])
print(data['included'])
```

### 4. Visual Regression Testing

Compare screenshots before and after changes:

1. Take screenshot of current implementation
2. Make your changes
3. Take new screenshot
4. Compare side-by-side

## Common Modifications

### Change Box Dimensions

```javascript
// In constructor
this.box_width = 250;   // Wider boxes
this.box_height = 100;  // Taller boxes
```

### Change Colour Scheme

```javascript
// In constructor
this.colors = {
    header: '#3498db',      // Blue header
    main_box: '#ecf0f1',    // Light grey boxes
    excluded_box: '#e74c3c', // Red exclusion boxes
    // ...
};
```

### Add Box Borders with Different Style

```javascript
draw_box(x, y, width, height, fill_color) {
    // Fill
    this.ctx.fillStyle = fill_color;
    this.ctx.fillRect(x, y, width, height);

    // Border with custom style
    this.ctx.strokeStyle = this.colors.border;
    this.ctx.lineWidth = 3;              // Thicker border
    this.ctx.setLineDash([5, 5]);        // Dashed border
    this.ctx.strokeRect(x, y, width, height);
    this.ctx.setLineDash([]);            // Reset to solid
}
```

### Dynamic Box Heights

```javascript
draw_exclusion_box(start_y, data) {
    const reason_count = Object.keys(data.exclusion_reasons || {}).length;
    const base_height = 80;
    const height_per_reason = 15;
    const box_height = base_height + (reason_count * height_per_reason);

    this.draw_box(x, start_y, this.box_width, box_height, color);
    // ... rest of drawing
}
```

## Debugging Tips

### 1. Enable Canvas Debugging

```javascript
draw(data) {
    console.log('Drawing PRISMA diagram with data:', data);

    // Draw with debug borders
    this.ctx.strokeStyle = 'red';
    this.ctx.strokeRect(0, 0, this.canvas.width, this.canvas.height);

    // Log positions
    console.log('Box position:', x, start_y);
}
```

### 2. Check Canvas Context

```javascript
if (!this.canvas || !this.ctx) {
    console.error('Canvas not properly initialised');
    return;
}
console.log('Canvas size:', this.canvas.width, 'x', this.canvas.height);
```

### 3. Verify Data

```javascript
draw(data) {
    // Validate data structure
    if (!data.identification) {
        console.warn('Missing identification data');
    }
    if (!data.retrieval) {
        console.warn('Missing retrieval data');
    }
    // ... continue drawing
}
```

### 4. Visual Alignment Guides

```javascript
// Draw centre line
this.ctx.strokeStyle = 'rgba(255, 0, 0, 0.3)';
this.ctx.beginPath();
this.ctx.moveTo(this.canvas.width / 2, 0);
this.ctx.lineTo(this.canvas.width / 2, this.canvas.height);
this.ctx.stroke();

// Draw grid
for (let i = 0; i < this.canvas.height; i += 50) {
    this.ctx.strokeStyle = 'rgba(0, 0, 255, 0.1)';
    this.ctx.beginPath();
    this.ctx.moveTo(0, i);
    this.ctx.lineTo(this.canvas.width, i);
    this.ctx.stroke();
}
```

## Performance Considerations

### Canvas Size

- Keep canvas dimensions reasonable (600x800 is optimal)
- Larger canvases increase render time and memory usage
- For high-DPI displays, scale canvas then transform back:

```javascript
const scale = window.devicePixelRatio;
this.canvas.width = 600 * scale;
this.canvas.height = 800 * scale;
this.canvas.style.width = '600px';
this.canvas.style.height = '800px';
this.ctx.scale(scale, scale);
```

### Efficient Rendering

- Minimize `fillText()` calls by batching similar text
- Use `save()` and `restore()` for context changes:

```javascript
this.ctx.save();
this.ctx.font = 'bold 12px Arial';
this.ctx.fillStyle = 'red';
// Draw with these settings
this.ctx.restore();  // Revert to previous settings
```

## Export Functionality

### PNG Export

```javascript
export_as_png(filename = 'diagram.png') {
    const link = document.createElement('a');
    link.download = filename;
    link.href = this.canvas.toDataURL('image/png');
    link.click();
}
```

### PDF Export

Requires jsPDF library:

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
```

```javascript
export_as_pdf(filename = 'diagram.pdf') {
    const img_data = this.canvas.toDataURL('image/png');
    const pdf = new jspdf.jsPDF();
    const img_width = 190;
    const img_height = (this.canvas.height * img_width) / this.canvas.width;
    pdf.addImage(img_data, 'PNG', 10, 10, img_width, img_height);
    pdf.save(filename);
}
```

## Integration with Django

### Template Usage

```html
<canvas id="prisma-diagram" width="600" height="800"></canvas>

<script src="{% static 'reporting/js/prisma2020.js' %}"></script>
<script>
    const diagram = new PRISMA2020Diagram('prisma-diagram');
    const data = {{ prisma_data|safe }};  // From Django context
    diagram.draw(data);
</script>
```

### View Integration

```python
from apps.reporting.services.prisma_reporting_service import PrismaReportingService

def prisma_diagram_view(request, session_id):
    service = PrismaReportingService()
    prisma_data = service.generate_prisma_flow_data(session_id)

    return render(request, 'reporting/prisma_diagram.html', {
        'prisma_data': json.dumps(prisma_data),
        'session_id': session_id
    })
```

## Troubleshooting

### Box Misalignment

**Problem**: Boxes not aligned properly in columns

**Solution**: Check that `left_x` calculation is consistent:
```javascript
const box_spacing = 40;
const total_width = (this.box_width * 2) + box_spacing;
const left_x = (this.canvas.width - total_width) / 2;
// Use this left_x for ALL left-aligned boxes
```

### Arrows Not Connecting

**Problem**: Arrows don't touch box edges

**Solution**: Ensure arrow coordinates match box positions:
```javascript
// Arrow FROM right edge of left box
const arrow_start_x = left_x + this.box_width;
// Arrow TO left edge of right box
const arrow_end_x = right_x;  // Not: right_x + some offset
```

### Text Overflow

**Problem**: Text exceeds box boundaries

**Solution**: Truncate or wrap text:
```javascript
const max_width = this.box_width - 20;  // Box width minus padding
const text = 'Very long reason name here';
const display_text = text.length > 25 ? text.substring(0, 22) + '...' : text;
this.ctx.fillText(display_text, x, y);
```

### Canvas Not Displaying

**Problem**: Canvas element is blank

**Checklist**:
1. Verify canvas element exists: `document.getElementById('canvas-id')`
2. Check console for errors
3. Ensure JavaScript loads after canvas element
4. Verify data is passed correctly
5. Check canvas has non-zero dimensions

## Best Practices

1. **Consistency**: Keep all left-aligned boxes using the same `left_x` calculation
2. **Modularity**: Create separate methods for each box type
3. **Comments**: Document complex positioning calculations
4. **Testing**: Test with edge cases (0 values, very large numbers)
5. **Validation**: Check data exists before accessing properties
6. **Fallbacks**: Provide default values for missing data
7. **Accessibility**: Consider adding ARIA labels for screen readers

## Further Reading

- [HTML5 Canvas API Documentation](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API)
- [PRISMA 2020 Official Guidelines](https://www.prisma-statement.org/prisma-2020)
- [Canvas Performance Tips](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas)

## Support

For issues or questions:
1. Check this guide
2. Review existing implementation in `prisma2020.js`
3. Test with standalone HTML file
4. Consult PRISMA 2020 official templates

---

**Last Updated**: 10 October 2025
**Maintainer**: Development Team
**Version**: 1.0
