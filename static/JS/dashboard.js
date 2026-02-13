
function getCurrentLocation() {
    let path = window.location.pathname.replace("/", "").toLowerCase();
    const valid = ["p2", "p3", "p4", "p5", "p6"];

    if (path === "dashboard" || path === "") return "";
    return valid.includes(path) ? path : "";
}

function changeLocation() {
    let selected = document.getElementById("locationFilter").value;
    window.location.href = selected === "" ? "/dashboard" : "/" + selected;
}

document.addEventListener("DOMContentLoaded", function () {
    let dropdown = document.getElementById("locationFilter");
    dropdown.value = getCurrentLocation();
    dropdown.addEventListener("change", changeLocation);
});

Chart.register(ChartDataLabels);

const pieChart = new Chart(document.getElementById('pieChart').getContext('2d'), {
    type: 'pie',
    data: {
        labels: ['Accepted', 'Rejected'],
        datasets: [{ data: [0, 0], backgroundColor: ['#B6F500', '#FF4444'] }]
    }
});

const barChart = new Chart(document.getElementById('barChart').getContext('2d'), {
    type: 'bar',
    data: {
        labels: ['Total', 'Accepted', 'Rejected'],
        datasets: [{
            label: 'Inspection Count',
            data: [0, 0, 0],
            backgroundColor: ['#8a2be2', '#56DFCF', 'red']
        }]
    },
    options: {
        plugins: {
            legend: {
                labels: {
                    font: {
                        weight: 'bold'
                    }
                }
            }
        },
        scales: {
            x: {
                ticks: {
                    font: {
                        weight: 'bold'
                    }
                }
            },
            y: {
                ticks: {
                    font: {
                        weight: 'bold'
                    }
                }
            }
        }
    }
});


function loadChartData() {

    let location = document.getElementById("locationFilter").value.trim();
    let part_number = document.getElementById("partFilter").value.trim();
    let shift = document.getElementById("shiftFilter").value.trim();
    let time = document.getElementById("timeFilter").value.trim();

    if (!location || location === "All Plants") location = "";
    if (!shift || shift === "All Shifts") shift = "";
    if (!part_number || part_number === "none" || part_number === "None") {
        part_number = "";
    }
    if (!time || time === "?" || time === "none") time = "daily";

    const url =
        `/api/chart-data?location=${encodeURIComponent(location)}`
        + `&part_number=${encodeURIComponent(part_number)}`
        + `&shift=${encodeURIComponent(shift)}`
        + `&time=${encodeURIComponent(time)}`;

    console.log("API URL:", url);

    fetch(url)
        .then(r => r.json())
        .then(data => {

            const accepted = data.accepted || 0;
            const rejected = data.rejected || 0;
            const total = data.total || 0;

            document.getElementById("acceptedCount").innerText = accepted;
            document.getElementById("rejectedCount").innerText = rejected;
            document.getElementById("totalCount").innerText = total;

            pieChart.data.datasets[0].data = [accepted, rejected];
            pieChart.update();

            barChart.data.datasets[0].data = [total, accepted, rejected];
            barChart.update();
        })
        .catch(err => console.error("Chart Load Error:", err));
}

function downloadDashboardReport() {
    let location = document.getElementById("locationFilter").value.trim();
    let shift = document.getElementById("shiftFilter").value.trim();
    let part_number = document.getElementById("partFilter").value.trim();
    let time_filter = document.getElementById("timeFilter").value.trim();


    if (!location || location === "All Plants") location = "";
    if (!shift || shift === "All Shifts") shift = "";
    if (!part_number || part_number.toLowerCase() === "none") part_number = "";
    if (!time_filter || time_filter === "?") time_filter = "daily";
    const url =
        `/api/reports/dashboard-download`
        + `?location=${encodeURIComponent(location)}`
        + `&shift=${encodeURIComponent(shift)}`
        + `&part_number=${encodeURIComponent(part_number)}`
        + `&time_filter=${encodeURIComponent(time_filter)}`;

    console.log("Auto-download with filters:", {
        location, shift, part_number, time_filter
    });
    window.location.href = url;
}


document.querySelectorAll('.filters select')
    .forEach(el => el.addEventListener('change', loadChartData));

window.onload = loadChartData;
setInterval(loadChartData, 1000);
