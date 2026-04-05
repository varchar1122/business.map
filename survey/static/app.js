document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("businessSurveyForm");
  const submitBtn = document.getElementById("submitSurveyBtn");
  const reportContainer = document.getElementById("reportContainer");
  const reportContent = document.getElementById("reportContent");
  const loadingIndicator = document.getElementById("loadingIndicator");

  // Функция показа ошибок
  function showError(inputId, errorId, message) {
    const input = document.getElementById(inputId);
    const errorDiv = document.getElementById(errorId);

    if (message) {
      input.classList.add("error");
      errorDiv.textContent = message;
      errorDiv.classList.add("show");
    } else {
      input.classList.remove("error");
      errorDiv.textContent = "";
      errorDiv.classList.remove("show");
    }
  }

  // Функция очистки всех ошибок
  function clearAllErrors() {
    showError("companyName", "companyNameError", "");
    showError("businessType", "businessTypeError", "");
    showError("region", "regionError", "");
  }

  // Функция отображения отчёта
  function displayReport(reportText) {
    // Преобразуем Markdown-подобные заголовки в HTML (простой вариант)
    let html = reportText
      .replace(/^## (.*$)/gim, "<h2>$1</h2>")
      .replace(/^### (.*$)/gim, "<h3>$1</h3>")
      .replace(/^\* (.*$)/gim, "<li>$1</li>")
      .replace(/\n\n/g, "</p><p>")
      .replace(/\n/g, "<br>");

    // Обернуть абзацы, если их нет
    if (!html.startsWith("<")) {
      html = "<p>" + html + "</p>";
    }
    // Улучшенная обработка списков
    html = html.replace(/<li>(.*?)<\/li>/g, "<ul><li>$1</li></ul>");
    html = html.replace(/<\/ul><ul>/g, "");

    reportContent.innerHTML = html;
    reportContainer.style.display = "block";
    // Прокрутка к отчёту
    reportContainer.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // Очистка предыдущего отчёта
  function clearReport() {
    reportContainer.style.display = "none";
    reportContent.innerHTML = "";
  }

  // Отправка формы
  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    // Очищаем ошибки и предыдущий отчёт
    clearAllErrors();
    clearReport();

    // Блокируем кнопку и показываем индикатор загрузки
    submitBtn.disabled = true;
    submitBtn.textContent = "ОТПРАВКА...";
    loadingIndicator.style.display = "block";

    // Собираем данные
    const formData = {
      companyName: document.getElementById("companyName").value.trim(),
      businessType: document.getElementById("businessType").value.trim(),
      region: document.getElementById("region").value.trim(),
      website: document.getElementById("website").value.trim(),
    };

    try {
      const response = await fetch("/api/submit-survey", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      });

      const result = await response.json();

      if (result.success) {
        // Отображаем полученный отчёт
        if (result.report) {
          displayReport(result.report);
        } else {
          displayReport("Отчёт не получен от сервера.");
        }
        // Очищаем форму (опционально)
        form.reset();
      } else {
        // Показываем ошибки валидации
        if (result.errors) {
          if (result.errors.companyName) {
            showError(
              "companyName",
              "companyNameError",
              result.errors.companyName,
            );
          }
          if (result.errors.businessType) {
            showError(
              "businessType",
              "businessTypeError",
              result.errors.businessType,
            );
          }
          if (result.errors.region) {
            showError("region", "regionError", result.errors.region);
          }
        } else if (result.error) {
          alert("Ошибка: " + result.error);
        } else {
          alert("Произошла ошибка при отправке формы");
        }
      }
    } catch (error) {
      console.error("Ошибка:", error);
      alert(
        "Ошибка соединения с сервером. Пожалуйста, проверьте что сервер запущен.",
      );
    } finally {
      // Разблокируем кнопку и скрываем загрузку
      submitBtn.disabled = false;
      submitBtn.textContent = "ОТПРАВИТЬ АНКЕТУ";
      loadingIndicator.style.display = "none";
    }
  });
});
