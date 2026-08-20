const { API_PATHS } = require("../../../utils/backend-config");
const { request } = require("../../../utils/request");

function normalizeMaintenance(record) {
  const source = record && typeof record === "object" ? record : {};
  return {
    id: String(source.id || "").trim(),
    date: String(source.date || "").trim(),
    item: String(source.item || "").trim(),
    mileage_km: String(source.mileage_km || "").trim(),
    cost: String(source.cost || "").trim(),
    note: String(source.note || "").trim(),
    updated_at: String(source.updated_at || "").trim(),
  };
}

function normalizeVehicle(vehicle) {
  const source = vehicle && typeof vehicle === "object" ? vehicle : {};
  const nickname = String(source.nickname || "").trim();
  const brand = String(source.brand || "").trim();
  const model = String(source.model || "").trim();
  const year = String(source.year || "").trim();
  const title = nickname || [brand, model].filter(Boolean).join(" ") || "我的爱车";
  const meta = [year, brand, model].filter(Boolean).join(" · ");
  const maintenance = normalizeMaintenance(
    source.maintenance
    || (Array.isArray(source.maintenance_records) && source.maintenance_records.length ? source.maintenance_records[0] : null),
  );
  const maintenanceSummary = maintenance.item
    ? [maintenance.date, maintenance.item, maintenance.mileage_km ? `${maintenance.mileage_km}km` : ""].filter(Boolean).join(" · ")
    : "暂无保养记录";
  return {
    id: String(source.id || "").trim(),
    nickname,
    brand,
    model,
    year,
    updated_at: String(source.updated_at || "").trim(),
    title,
    meta,
    maintenance,
    maintenanceSummary,
    maintenance_count: maintenance.item ? 1 : 0,
  };
}

function emptyVehicleDraft() {
  return {
    nickname: "",
    maintenance_date: "",
    maintenance_item: "",
    maintenance_mileage_km: "",
    maintenance_note: "",
  };
}

Page({
  data: {
    loading: true,
    saving: false,
    error: "",
    vehicles: [],
    showVehicleEditor: false,
    vehicleEditorTitle: "新增爱车",
    editingVehicleId: "",
    vehicleDraft: emptyVehicleDraft(),
  },

  onLoad() {
    this.fetchVehicles();
  },

  onShow() {
    this.fetchVehicles();
  },

  onPullDownRefresh() {
    this.fetchVehicles(true);
  },

  fetchVehicles(stopRefresh = false) {
    this.setData({ loading: true, error: "" });
    request({ path: API_PATHS.meVehicles })
      .then((payload) => {
        const source = Array.isArray(payload?.vehicles) ? payload.vehicles : [];
        this.setData({
          loading: false,
          error: "",
          vehicles: source.map(normalizeVehicle),
        });
      })
      .catch((error) => {
        this.setData({
          loading: false,
          error: error?.message || "加载爱车信息失败",
          vehicles: [],
        });
      })
      .finally(() => {
        if (stopRefresh) {
          wx.stopPullDownRefresh();
        }
      });
  },

  handleOpenCreateVehicle() {
    this.setData({
      showVehicleEditor: true,
      vehicleEditorTitle: "新增爱车",
      editingVehicleId: "",
      vehicleDraft: emptyVehicleDraft(),
    });
  },

  handleOpenEditVehicle(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    const vehicle = (this.data.vehicles || []).find((item) => item.id === vehicleId);
    if (!vehicle) {
      return;
    }

    const maintenance = vehicle.maintenance || {};
    this.setData({
      showVehicleEditor: true,
      vehicleEditorTitle: "编辑爱车",
      editingVehicleId: vehicleId,
      vehicleDraft: {
        nickname: vehicle.nickname,
        maintenance_date: maintenance.date || "",
        maintenance_item: maintenance.item || "",
        maintenance_mileage_km: maintenance.mileage_km || "",
        maintenance_note: maintenance.note || "",
      },
    });
  },

  handleOpenUpdateMaintenance(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    const vehicle = (this.data.vehicles || []).find((item) => item.id === vehicleId);
    if (!vehicle) {
      return;
    }

    const maintenance = vehicle.maintenance || {};
    this.setData({
      showVehicleEditor: true,
      vehicleEditorTitle: "更新保养",
      editingVehicleId: vehicleId,
      vehicleDraft: {
        nickname: vehicle.nickname,
        maintenance_date: maintenance.date || "",
        maintenance_item: maintenance.item || "",
        maintenance_mileage_km: maintenance.mileage_km || "",
        maintenance_note: maintenance.note || "",
      },
    });
  },

  handleCloseVehicleEditor() {
    this.setData({
      showVehicleEditor: false,
      editingVehicleId: "",
      vehicleDraft: emptyVehicleDraft(),
    });
  },

  handleVehicleDraftInput(event) {
    const field = String(event?.currentTarget?.dataset?.field || "").trim();
    if (!field) {
      return;
    }

    this.setData({
      vehicleDraft: {
        ...(this.data.vehicleDraft || emptyVehicleDraft()),
        [field]: String(event?.detail?.value || "").trim(),
      },
    });
  },

  handleSaveVehicle() {
    if (this.data.saving) {
      return;
    }

    const draft = this.data.vehicleDraft || emptyVehicleDraft();
    if (!String(draft.nickname || "").trim()) {
      wx.showToast({ title: "请填写爱车名称", icon: "none" });
      return;
    }

    this.setData({ saving: true });

    const editingVehicleId = String(this.data.editingVehicleId || "").trim();
    const isEditing = Boolean(editingVehicleId);
    request({
      path: isEditing ? API_PATHS.meVehicle(editingVehicleId) : API_PATHS.meVehicles,
      method: isEditing ? "PUT" : "POST",
      data: draft,
    })
      .then((payload) => {
        if (!payload?.ok) {
          wx.showToast({ title: String(payload?.error || "保存失败"), icon: "none" });
          return;
        }

        wx.showToast({ title: isEditing ? "已更新" : "已新增", icon: "success" });
        this.handleCloseVehicleEditor();
        this.fetchVehicles();
      })
      .catch((error) => {
        wx.showToast({ title: error?.message || "保存失败", icon: "none" });
      })
      .finally(() => {
        this.setData({ saving: false });
      });
  },

  handleDeleteVehicle(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    if (!vehicleId) {
      return;
    }

    wx.showModal({
      title: "删除爱车",
      content: "删除后该车保养记录也会一并清空，确认删除？",
      success: (result) => {
        if (!result.confirm) {
          return;
        }

        request({
          path: API_PATHS.meVehicle(vehicleId),
          method: "DELETE",
        })
          .then((payload) => {
            if (!payload?.ok) {
              wx.showToast({ title: String(payload?.error || "删除失败"), icon: "none" });
              return;
            }
            wx.showToast({ title: "已删除", icon: "success" });
            this.fetchVehicles();
          })
          .catch((error) => {
            wx.showToast({ title: error?.message || "删除失败", icon: "none" });
          });
      },
    });
  },

  noop() {},
});
