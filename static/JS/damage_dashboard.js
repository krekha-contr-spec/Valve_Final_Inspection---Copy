let defectChart = null;

async function fetchDefectTypes(partNumber = "", timeFilter = "") {
    try {
        const url = `/api/defect-types?part=${encodeURIComponent(partNumber)}&time=${encodeURIComponent(timeFilter)}`;
        const response = await fetch(url);
        const result = await response.json();

        if (result.error) {
            console.error("Defect API error:", result.error);
            return;
        }

        if (document.getElementById("selectedFilters")) {
            document.getElementById("selectedFilters").innerText =
                `Part Number: ${partNumber || "All"} | Time Filter: ${timeFilter || "All"}`;
        }

        const data = result.data || [];

        const defectOrder = [
            "Face Damage", "Head Damage", "Seat Damage", "Neck Damage",
            "Stem Damage", "Groove Damage", "End Chamfer", "Tip End",
            "Bent Valve", "Crack", "Scratch", "Discoloration", "Radius Damage"
        ];

        const colorMap = {
            "Face Damage": "yellow",
            "Head Damage": "#03A6A1",
            "Seat Damage": "#FF2DD1",
            "Neck Damage": "#FE7743",
            "Stem Damage": "#81E7AF",
            "Groove Damage": "#901E3E",
            "End Chamfer": "#008080",
            "Tip End": "blue",
            "Bent Valve": "#B7B1F2",
            "Crack": "green",
            "Scratch": "#B771E5",
            "Discoloration": "skyblue",
            "Radius Damage": "#FFA500"
        };

        const labelMap = {
            "Face_Damage": "Face Damage",
            "Head_Damage": "Head Damage",
            "Seat_Damage": "Seat Damage",
            "Neck_Damage": "Neck Damage",
            "Stem_Damage": "Stem Damage",
            "Groove_Damage": "Groove Damage",
            "End_Chamfer": "End Chamfer",
            "Tip_Damage": "Tip End",
            "Tip_End": "Tip End",
            "Bend_Damage": "Bent Valve",
            "Bent_Valve": "Bent Valve",
            "Crack_Damage": "Crack",
            "Scratch_Damage": "Scratch",
            "Discoloration_Damage": "Discoloration",
            "Radius_Damage": "Radius Damage"
        };

        const defectCountMap = {};
        data.forEach(item => {
            if (item.label) {
                const standardLabel = labelMap[item.label.trim()] || item.label.trim();
                defectCountMap[standardLabel] = (defectCountMap[standardLabel] || 0) + Math.round(item.count);
            }
        });

        const counts = defectOrder.map(defect => defectCountMap[defect] || 0);
        const colors = defectOrder.map(defect => colorMap[defect] || "purple");

        const ctx = document.getElementById('defectBarChart').getContext('2d');

        if (defectChart) {
            defectChart.data.datasets[0].data = counts;
            defectChart.update();
        } else {
            defectChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: defectOrder,
                    datasets: [{
                        label: 'Count',
                        data: counts,
                        backgroundColor: colors,
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            ticks: { color: '#212121', font: { weight: 'bold' } },
                            title: {
                                display: true,
                                text: 'Defect Type',
                                color: 'green',
                                font: { weight: 'bold', size: 20, style: 'italic' }
                            }
                        },
                        y: {
                            beginAtZero: true,
                            ticks: { stepSize: 1, color: '#212121' },
                            title: {
                                display: true,
                                text: 'Count',
                                color: 'green',
                                font: { weight: 'bold', size: 20, style: 'italic' }
                            }
                        }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }
    } catch (err) {
        console.error("Defect chart fetch error:", err);
    }
}

function loadChart() {
    let partNumber = document.getElementById("partFilter")?.value || "";
    let timeFilter = document.getElementById("timeFilter")?.value || "";

    if (partNumber.toLowerCase() === "none") partNumber = "";
    if (timeFilter.toLowerCase() === "none") timeFilter = "";

    fetchDefectTypes(partNumber, timeFilter);
}

window.onload = loadChart;
setInterval(loadChart, 10000);

document.getElementById("partFilter")?.addEventListener("change", loadChart);
document.getElementById("timeFilter")?.addEventListener("change", loadChart);
