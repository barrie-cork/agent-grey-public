/**
 * PRISMA 2020 Canvas Diagram Module
 * Renders PRISMA 2020 flow diagram for "Identification of new studies via databases and registers"
 */

class PRISMA2020Diagram {
    constructor(canvas_id) {
        this.canvas = document.getElementById(canvas_id);

        // Check if canvas element exists
        if (!this.canvas) {
            console.error(`Canvas element with ID '${canvas_id}' not found`);
            return;
        }

        this.ctx = this.canvas.getContext('2d');
        if (!this.ctx) {
            console.error(`Unable to get 2D context for canvas '${canvas_id}'`);
            return;
        }

        // Layout constants
        this.padding = 40;
        this.box_width = 220;
        this.box_height = 80;
        this.arrow_size = 6;
        this.font_size = 10;
        this.title_font_size = 14;
        this.header_font_size = 12;
        this.vertical_spacing = 25;

        // Text alignment constants
        this.text_left_margin = 8;
        this.text_indent = 20;

        // Colors
        this.colors = {
            header: '#ffc107',
            main_box: '#ffffff',
            excluded_box: '#ffffff',
            included_box: '#ffffff',
            text: '#000000',
            border: '#000000',
            arrow: '#000000'
        };
    }

    /**
     * Draw the complete PRISMA 2020 database flow diagram
     */
    draw(data) {
        if (!this.canvas || !this.ctx) {
            console.error('Canvas not properly initialized. Cannot draw diagram.');
            return;
        }

        // Set canvas size - taller to fit screening row
        this.canvas.width = 600;
        this.canvas.height = 950;

        // Clear canvas and set white background
        this.ctx.fillStyle = '#ffffff';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Draw title
        this.draw_title();

        // Draw header section
        this.draw_header();

        // Draw identification box
        const ident_y = this.draw_identification_box(data.identification);

        // Draw "records removed before screening" box
        const removed_y = this.draw_records_removed_box(ident_y + this.vertical_spacing, data.screening);

        // Draw screening row
        const screening_y = this.draw_screening_boxes(removed_y + this.vertical_spacing, data.screening);

        // Draw retrieval boxes
        const retrieval_y = this.draw_retrieval_boxes(screening_y + this.vertical_spacing, data.retrieval);

        // Draw eligibility boxes
        const eligibility_y = this.draw_eligibility_boxes(retrieval_y + this.vertical_spacing, data.eligibility);

        // Draw studies included box
        const final_y = eligibility_y + this.vertical_spacing;
        const box_spacing = 40;
        const total_width = (this.box_width * 2) + box_spacing;
        const left_x = (this.canvas.width - total_width) / 2;
        this.draw_studies_included_box(left_x, final_y, data.included);
    }

    draw_title() {
        this.ctx.font = `bold ${this.title_font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'center';
        this.ctx.fillText('PRISMA 2020 Flow Diagram', this.canvas.width / 2, 30);
    }

    draw_header() {
        const header_y = 45;
        const header_height = 30;
        const header_width = this.canvas.width - (this.padding * 2);

        this.ctx.fillStyle = this.colors.header;
        this.ctx.fillRect(this.padding, header_y, header_width, header_height);

        this.ctx.strokeStyle = this.colors.border;
        this.ctx.lineWidth = 2;
        this.ctx.strokeRect(this.padding, header_y, header_width, header_height);

        this.ctx.font = `bold ${this.header_font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'center';
        this.ctx.fillText('Identification of new studies via databases and registers', this.canvas.width / 2, header_y + 20);
    }

    draw_identification_box(data) {
        const start_y = 90;
        const box_spacing = 40;
        const total_width = (this.box_width * 2) + box_spacing;
        const left_x = (this.canvas.width - total_width) / 2;
        const box_height = this.box_height;

        this.draw_box(left_x, start_y, this.box_width, box_height, this.colors.main_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const text_x = left_x + this.text_left_margin;
        const indent_x = left_x + this.text_indent;

        this.ctx.fillText('Records identified from:', text_x, start_y + 20);
        this.ctx.fillText(`Databases (n = ${data.databases || 0})`, indent_x, start_y + 36);
        this.ctx.fillText(`Registers (n = ${data.registers || 0})`, indent_x, start_y + 52);

        // Arrow down
        const box_center_x = left_x + this.box_width / 2;
        const arrow_start_y = start_y + box_height;
        const arrow_end_y = arrow_start_y + this.vertical_spacing;
        this.draw_arrow(box_center_x, arrow_start_y, box_center_x, arrow_end_y);

        return arrow_end_y;
    }

    draw_records_removed_box(start_y, data) {
        const box_spacing = 40;
        const total_width = (this.box_width * 2) + box_spacing;
        const left_x = (this.canvas.width - total_width) / 2;
        const box_height = 60;

        this.draw_box(left_x, start_y, this.box_width, box_height, this.colors.main_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const text_x = left_x + this.text_left_margin;
        const indent_x = left_x + this.text_indent;

        this.ctx.fillText('Records removed before screening:', text_x, start_y + 20);
        this.ctx.fillText(`Duplicate records (n = ${data.duplicates_removed || 0})`, indent_x, start_y + 38);

        // Arrow down
        const box_center_x = left_x + this.box_width / 2;
        const arrow_start_y = start_y + box_height;
        const arrow_end_y = arrow_start_y + this.vertical_spacing;
        this.draw_arrow(box_center_x, arrow_start_y, box_center_x, arrow_end_y);

        return arrow_end_y;
    }

    draw_screening_boxes(start_y, data) {
        const box_spacing = 40;
        const total_width = (this.box_width * 2) + box_spacing;
        const left_x = (this.canvas.width - total_width) / 2;
        const right_x = left_x + this.box_width + box_spacing;

        // Left box: Records screened
        this.draw_box(left_x, start_y, this.box_width, this.box_height, this.colors.main_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const left_text_x = left_x + this.text_left_margin;
        this.ctx.fillText('Records screened', left_text_x, start_y + 30);
        this.ctx.fillText(`(n = ${data.records_screened || 0})`, left_text_x, start_y + 45);

        // Arrow to right box
        this.draw_arrow(left_x + this.box_width, start_y + this.box_height / 2, right_x, start_y + this.box_height / 2);

        // Right box: Records excluded
        this.draw_box(right_x, start_y, this.box_width, this.box_height, this.colors.excluded_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const right_text_x = right_x + this.text_left_margin;
        this.ctx.fillText('Records excluded', right_text_x, start_y + 30);
        this.ctx.fillText(`(n = ${data.records_excluded || 0})`, right_text_x, start_y + 45);

        // Arrow down from left box
        const left_center_x = left_x + this.box_width / 2;
        const arrow_start_y = start_y + this.box_height;
        const arrow_end_y = arrow_start_y + this.vertical_spacing;
        this.draw_arrow(left_center_x, arrow_start_y, left_center_x, arrow_end_y);

        return arrow_end_y;
    }

    draw_retrieval_boxes(start_y, data) {
        const box_spacing = 40;
        const total_width = (this.box_width * 2) + box_spacing;
        const left_x = (this.canvas.width - total_width) / 2;
        const right_x = left_x + this.box_width + box_spacing;

        this.draw_box(left_x, start_y, this.box_width, this.box_height, this.colors.main_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const left_text_x = left_x + this.text_left_margin;
        this.ctx.fillText('Reports sought for retrieval', left_text_x, start_y + 30);
        this.ctx.fillText(`(n = ${data.reports_sought || 0})`, left_text_x, start_y + 45);

        this.draw_arrow(left_x + this.box_width, start_y + this.box_height / 2, right_x, start_y + this.box_height / 2);

        this.draw_box(right_x, start_y, this.box_width, this.box_height, this.colors.excluded_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const right_text_x = right_x + this.text_left_margin;
        this.ctx.fillText('Reports not retrieved', right_text_x, start_y + 30);
        this.ctx.fillText(`(n = ${data.reports_not_retrieved || 0})`, right_text_x, start_y + 45);

        const left_center_x = left_x + this.box_width / 2;
        const arrow_start_y = start_y + this.box_height;
        const arrow_end_y = arrow_start_y + this.vertical_spacing;
        this.draw_arrow(left_center_x, arrow_start_y, left_center_x, arrow_end_y);

        return arrow_end_y;
    }

    draw_eligibility_boxes(start_y, data) {
        const box_spacing = 40;
        const total_width = (this.box_width * 2) + box_spacing;
        const left_x = (this.canvas.width - total_width) / 2;
        const right_x = left_x + this.box_width + box_spacing;

        this.draw_box(left_x, start_y, this.box_width, this.box_height, this.colors.main_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const left_text_x = left_x + this.text_left_margin;
        this.ctx.fillText('Reports assessed for eligibility', left_text_x, start_y + 30);
        this.ctx.fillText(`(n = ${data.reports_assessed || 0})`, left_text_x, start_y + 45);

        this.draw_arrow(left_x + this.box_width, start_y + this.box_height / 2, right_x, start_y + this.box_height / 2);

        // Excluded box (taller for exclusion reasons)
        const excluded_box_height = this.box_height + 30;
        this.draw_box(right_x, start_y, this.box_width, excluded_box_height, this.colors.excluded_box);

        this.ctx.font = `${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const right_text_x = right_x + this.text_left_margin;
        const right_indent_x = right_x + this.text_indent;

        this.ctx.fillText(`Reports excluded (n = ${data.excluded || 0}):`, right_text_x, start_y + 20);

        const reasons = data.exclusion_reasons || {};
        const reason_entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 3);

        this.ctx.font = `9px Arial`;
        if (reason_entries.length > 0) {
            let reason_y = start_y + 35;
            for (const [reason, count] of reason_entries) {
                const display_reason = reason.length > 18 ? reason.substring(0, 15) + '...' : reason;
                this.ctx.fillText(`  ${display_reason} (n = ${count})`, right_indent_x, reason_y);
                reason_y += 13;
            }
        } else {
            this.ctx.fillText('  Reason 1 (n = )', right_indent_x, start_y + 35);
            this.ctx.fillText('  Reason 2 (n = )', right_indent_x, start_y + 48);
            this.ctx.fillText('  Reason 3 (n = )', right_indent_x, start_y + 61);
        }

        const left_center_x = left_x + this.box_width / 2;
        const arrow_start_y = start_y + this.box_height;
        const arrow_end_y = arrow_start_y + this.vertical_spacing;
        this.draw_arrow(left_center_x, arrow_start_y, left_center_x, arrow_end_y);

        return arrow_end_y;
    }

    draw_studies_included_box(x, start_y, data) {
        this.draw_box(x, start_y, this.box_width, this.box_height, this.colors.included_box);

        this.ctx.font = `bold ${this.font_size}px Arial`;
        this.ctx.fillStyle = this.colors.text;
        this.ctx.textAlign = 'left';

        const text_x = x + this.text_left_margin;
        this.ctx.fillText('New studies included in review', text_x, start_y + 35);
        this.ctx.fillText(`(n = ${data.total || 0})`, text_x, start_y + 55);
    }

    draw_box(x, y, width, height, fill_color) {
        this.ctx.fillStyle = fill_color;
        this.ctx.fillRect(x, y, width, height);

        this.ctx.strokeStyle = this.colors.border;
        this.ctx.lineWidth = 1;
        this.ctx.strokeRect(x, y, width, height);
    }

    draw_arrow(from_x, from_y, to_x, to_y) {
        this.ctx.beginPath();
        this.ctx.moveTo(from_x, from_y);
        this.ctx.lineTo(to_x, to_y);
        this.ctx.strokeStyle = this.colors.arrow;
        this.ctx.lineWidth = 2;
        this.ctx.stroke();

        const angle = Math.atan2(to_y - from_y, to_x - from_x);
        this.ctx.beginPath();
        this.ctx.moveTo(to_x, to_y);
        this.ctx.lineTo(
            to_x - this.arrow_size * Math.cos(angle - Math.PI / 6),
            to_y - this.arrow_size * Math.sin(angle - Math.PI / 6)
        );
        this.ctx.moveTo(to_x, to_y);
        this.ctx.lineTo(
            to_x - this.arrow_size * Math.cos(angle + Math.PI / 6),
            to_y - this.arrow_size * Math.sin(angle + Math.PI / 6)
        );
        this.ctx.stroke();
    }

    /**
     * Export canvas as PNG
     */
    export_as_png(filename = 'prisma-2020-diagram.png') {
        const link = document.createElement('a');
        link.download = filename;
        link.href = this.canvas.toDataURL();
        link.click();
    }

    /**
     * Export canvas as PDF using jsPDF
     */
    export_as_pdf(filename = 'prisma-2020-diagram.pdf') {
        if (typeof jspdf === 'undefined') {
            console.error('jsPDF library not loaded');
            return;
        }

        const img_data = this.canvas.toDataURL('image/png');
        const pdf = new jspdf.jsPDF();
        const img_width = 190;
        const img_height = (this.canvas.height * img_width) / this.canvas.width;

        pdf.addImage(img_data, 'PNG', 10, 10, img_width, img_height);
        pdf.save(filename);
    }

    /**
     * Get canvas as data URL
     */
    get_data_url() {
        return this.canvas.toDataURL();
    }

    /**
     * Alias methods for camelCase compatibility
     */
    exportAsPNG(filename = 'prisma-2020-diagram.png') {
        return this.export_as_png(filename);
    }

    exportAsPDF(filename = 'prisma-2020-diagram.pdf') {
        return this.export_as_pdf(filename);
    }

    getDataURL() {
        return this.get_data_url();
    }
}

// Export for use in other modules
window.PRISMA2020Diagram = PRISMA2020Diagram;
