/**
 * 鸿图建材获客工具 — 前端交互
 */
document.addEventListener('DOMContentLoaded', function () {

    // ===== 1. 删除确认弹窗 =====
    // 所有带 delete-form 类的表单提交时弹出确认
    document.addEventListener('submit', function (e) {
        if (e.target.classList.contains('delete-form')) {
            var btn = e.target.querySelector('[data-customer]');
            var name = btn ? btn.dataset.customer : '该客户';
            if (!confirm('确定要删除"' + name + '"吗？\n删除后无法恢复，相关的跟进记录也会一并删除。')) {
                e.preventDefault();
            }
        }
    });

    // ===== 2. 表单必填验证 =====
    // 所有带 needs-validation 类的表单使用 Bootstrap 原生验证
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (form.classList.contains('needs-validation')) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        }
    });

    // ===== 3. 导入文件选择后自动提交 =====
    var importForm = document.getElementById('importForm');
    if (importForm) {
        var fileInput = importForm.querySelector('input[type="file"]');
        if (fileInput) {
            fileInput.addEventListener('change', function () {
                if (this.files && this.files.length > 0) {
                    // 简单校验文件后缀
                    var name = this.files[0].name.toLowerCase();
                    if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
                        importForm.submit();
                    } else {
                        alert('请选择 .xlsx 格式的Excel文件');
                        this.value = '';
                    }
                }
            });
        }
    }

    // ===== 4. 状态切换 AJAX =====
    var statusSelect = document.getElementById('statusSelect');
    if (statusSelect) {
        statusSelect.addEventListener('change', function () {
            var customerId = this.dataset.customerId;
            var newStatus = this.value;

            var formData = new FormData();
            formData.append('status', newStatus);

            fetch('/customers/' + customerId + '/status', {
                method: 'POST',
                body: formData,
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.success) {
                        alert('状态已更新为：' + data.status);
                        location.reload();
                    } else {
                        alert('更新失败：' + data.message);
                        location.reload();
                    }
                })
                .catch(function () {
                    alert('网络错误，请重试');
                    location.reload();
                });
        });
    }

    // ===== 5. Flash 消息自动消失 =====
    var alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 4000);
    });

});
