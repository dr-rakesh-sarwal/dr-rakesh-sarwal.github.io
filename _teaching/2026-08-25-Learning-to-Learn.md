---
title: "Learning to Learn: A Framework for Self-Directed Knowledge Management in Medical and Public Health Education"
type: "Postgraduate Seminar"
permalink: /teaching/2026-Learning-to-Learn
venue: "ESIC Medical College"
date: 2026-08-24
location: "Faridabad"
---
Efficient knowledge processing is essential for survival and growth in today’s fast-paced, information-overloaded world. This is particularly important for academics and students. Learning begins with self-awareness and a basic understanding of the world around us.

This lecture presents a collection of tools and techniques for developing an efficient personal knowledge-management and information-processing system. It covers clarifying life goals, practising self-care, understanding and making effective use of time-based learning, recognising the power of nature, understanding the broader environment and its key drivers, learning foundational concepts, developing metacognition, and using practical tools to learn more effectively.

This presentation was used to teach MD(Community Medicine) students.
--
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cross-Platform PDF Viewer</title>
  <!-- Load PDF.js CDN -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <style>
    .pdf-wrapper {
      width: 100%;
      max-width: 800px;
      margin: 0 auto;
      overflow-x: auto;
    }
    #pdf-render {
      width: 100%;
      height: auto;
      border: 1px solid #ccc;
    }
  </style>
</head>
<body>

  <div class="pdf-wrapper">
    <canvas id="pdf-render"></canvas>
  </div>

  <script>
    // Specify path to worker
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    const url ="/files/learning-how-to-learn.pdf"; // URL to your PDF file

    // Asynchronously download PDF
    pdfjsLib.getDocument(url).promise.then(pdf => {
      // Fetch the first page
      pdf.getPage(1).then(page => {
        const canvas = document.getElementById('pdf-render');
        const ctx = canvas.getContext('2d');

        const viewport = page.getViewport({ scale: 1.5 });
        canvas.height = viewport.height;
        canvas.width = viewport.width;

        // Render PDF page into canvas context
        const renderContext = {
          canvasContext: ctx,
          viewport: viewport
        };
        page.render(renderContext);
      });
    });
  </script>
</body>
</html>
![Lecture](/images/learning-how-to-learn.jpeg)
