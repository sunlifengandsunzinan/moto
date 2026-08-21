const { API_PATHS } = require("../../../utils/backend-config");
const { request } = require("../../../utils/request");

function normalizeMaintenance(record) {
  const source = record && typeof record === "object" ? record : {};
  return {
    id: String(source.id || "").trim(),
    date: String(source.date || "").trim(),
    item: String(source.item || "").trim(),
    location: String(source.location || "").trim(),
    mileage_km: String(source.mileage_km || "").trim(),
    cost: String(source.cost || "").trim(),
    note: String(source.note || "").trim(),
    updated_at: String(source.updated_at || "").trim(),
  };
}

function normalizeVehicle(vehicle) {
  const source = vehicle && typeof vehicle === "object" ? vehicle : {};
  const rawRecords = Array.isArray(source.maintenance_records)
    ? source.maintenance_records.map(normalizeMaintenance).filter((item) => item.item)
    : [];
  const latestMaintenance = normalizeMaintenance(source.maintenance || rawRecords[0] || null);
  const records = rawRecords.length
    ? rawRecords
    : (latestMaintenance.item ? [latestMaintenance] : []);
  const nickname = String(source.nickname || "").trim();
  const brand = String(source.brand || "").trim();
  const model = String(source.model || "").trim();
  const year = String(source.year || "").trim();
  const title = model || nickname || [brand, model].filter(Boolean).join(" ") || "爱车保养";
  const meta = [year, brand, model].filter(Boolean).join(" · ");
  const maintenanceSummary = latestMaintenance.item
    ? [latestMaintenance.date, latestMaintenance.item, latestMaintenance.mileage_km ? `${latestMaintenance.mileage_km}km` : ""].filter(Boolean).join(" · ")
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
    maintenance: latestMaintenance,
    maintenance_records: records,
    maintenanceSummary,
    maintenance_count: records.length,
  };
}

function emptyVehicleDraft() {
  return {
    model: "",
  };
}

function emptyMaintenanceDraft() {
  return {
    date: "",
    item: "",
    location: "",
    mileage_km: "",
    cost: "",
    note: "",
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
    showMaintenanceEditor: false,
    maintenanceEditorTitle: "新增保养",
    activeVehicleId: "",
    maintenanceDraft: emptyMaintenanceDraft(),
    maintenanceExpandedMap: {},
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
        const previousExpandedMap = this.data.maintenanceExpandedMap || {};
        const vehicles = source.map(normalizeVehicle).map((item) => {
          const hasStoredExpanded = Object.prototype.hasOwnProperty.call(previousExpandedMap, item.id);
          return {
            ...item,
            maintenance_expanded: hasStoredExpanded ? Boolean(previousExpandedMap[item.id]) : true,
          };
        });
        this.setData({
          loading: false,
          error: "",
          vehicles,
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

  openVehicleEditorById(vehicleId, title) {
    const normalizedVehicleId = String(vehicleId || "").trim();
    if (!normalizedVehicleId) {
      return;
    }

    const vehicle = (this.data.vehicles || []).find((item) => item.id === normalizedVehicleId);
    if (!vehicle) {
      return;
    }

    this.setData({
      showVehicleEditor: true,
      vehicleEditorTitle: String(title || "更新"),
      editingVehicleId: normalizedVehicleId,
      vehicleDraft: {
        model: vehicle.model || vehicle.nickname || "",
      },
    });
  },

  openMaintenanceEditorByVehicleId(vehicleId) {
    const normalizedVehicleId = String(vehicleId || "").trim();
    if (!normalizedVehicleId) {
      return;
    }

    const vehicle = (this.data.vehicles || []).find((item) => item.id === normalizedVehicleId);
    if (!vehicle) {
      return;
    }

    this.setData({
      showMaintenanceEditor: true,
      maintenanceEditorTitle: `新增保养 · ${vehicle.title}`,
      activeVehicleId: normalizedVehicleId,
      maintenanceDraft: emptyMaintenanceDraft(),
    });
  },

  handleOpenUpdateActions(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    if (!vehicleId) {
      return;
    }

    wx.showActionSheet({
      itemList: ["编辑车型号", "删除爱车"],
      success: (result) => {
        const tapIndex = Number(result?.tapIndex);
        if (tapIndex === 0) {
          this.openVehicleEditorById(vehicleId, "编辑车型号");
          return;
        }
        if (tapIndex === 1) {
          this.handleDeleteVehicleById(vehicleId);
        }
      },
    });
  },

  handleToggleMaintenance(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    if (!vehicleId) {
      return;
    }

    const expandedMap = {
      ...(this.data.maintenanceExpandedMap || {}),
      [vehicleId]: !Boolean((this.data.maintenanceExpandedMap || {})[vehicleId]),
    };
    const vehicles = (this.data.vehicles || []).map((item) => {
      if (item.id !== vehicleId) {
        return item;
      }
      return {
        ...item,
        maintenance_expanded: Boolean(expandedMap[vehicleId]),
      };
    });

    this.setData({
      maintenanceExpandedMap: expandedMap,
      vehicles,
    });
  },

  handleOpenMaintenanceEditor(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    if (!vehicleId) {
      return;
    }
    this.openMaintenanceEditorByVehicleId(vehicleId);
  },

  handleDeleteMaintenanceRecord(event) {
    const vehicleId = String(event?.currentTarget?.dataset?.vehicleId || "").trim();
    const recordId = String(event?.currentTarget?.dataset?.recordId || "").trim();
    if (!vehicleId || !recordId) {
      wx.showToast({ title: "记录缺少ID，无法删除", icon: "none" });
      return;
    }

    wx.showModal({
      title: "删除保养记录",
      content: "确认删除这条保养记录？",
      success: (result) => {
        if (!result.confirm) {
          return;
        }

        request({
          path: API_PATHS.meVehicleMaintenanceRecord(vehicleId, recordId),
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

  handleDeleteVehicleById(vehicleId) {
    const normalizedVehicleId = String(vehicleId || "").trim();
    if (!normalizedVehicleId) {
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
          path: API_PATHS.meVehicle(normalizedVehicleId),
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

  handleCloseVehicleEditor() {
    this.setData({
      showVehicleEditor: false,
      editingVehicleId: "",
      vehicleDraft: emptyVehicleDraft(),
    });
  },

  handleCloseMaintenanceEditor() {
    this.setData({
      showMaintenanceEditor: false,
      maintenanceEditorTitle: "新增保养",
      activeVehicleId: "",
      maintenanceDraft: emptyMaintenanceDraft(),
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

  handleMaintenanceDraftInput(event) {
    const field = String(event?.currentTarget?.dataset?.field || "").trim();
    if (!field) {
      return;
    }

    this.setData({
      maintenanceDraft: {
        ...(this.data.maintenanceDraft || emptyMaintenanceDraft()),
        [field]: String(event?.detail?.value || "").trim(),
      },
    });
  },

  handleSaveVehicle() {
    if (this.data.saving) {
      return;
    }

    const draft = this.data.vehicleDraft || emptyVehicleDraft();
    const model = String(draft.model || "").trim();
    if (!model) {
      wx.showToast({ title: "请填写车型号", icon: "none" });
      return;
    }

    this.setData({ saving: true });

    const editingVehicleId = String(this.data.editingVehicleId || "").trim();
    const isEditing = Boolean(editingVehicleId);
    request({
      path: isEditing ? API_PATHS.meVehicle(editingVehicleId) : API_PATHS.meVehicles,
      method: isEditing ? "PUT" : "POST",
      data: {
        model,
        nickname: model,
      },
    })
      .then((payload) => {
        if (!payload?.ok) {
          wx.showToast({ title: String(payload?.error || "保存失败"), icon: "none" });
          return;
        }

        wx.showToast({ title: isEditing ? "车型号已更新" : "爱车已新增", icon: "success" });
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

  handleSaveMaintenance() {
    if (this.data.saving) {
      return;
    }

    const vehicleId = String(this.data.activeVehicleId || "").trim();
    if (!vehicleId) {
      return;
    }

    const draft = this.data.maintenanceDraft || emptyMaintenanceDraft();
    if (!String(draft.item || "").trim()) {
      wx.showToast({ title: "请填写保养项目", icon: "none" });
      return;
    }

    this.setData({ saving: true });
    request({
      path: API_PATHS.meVehicleMaintenance(vehicleId),
      method: "POST",
      data: draft,
    })
      .then((payload) => {
        if (!payload?.ok) {
          wx.showToast({ title: String(payload?.error || "保存失败"), icon: "none" });
          return;
        }

        wx.showToast({ title: "保养记录已新增", icon: "success" });
        this.handleCloseMaintenanceEditor();
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
    this.handleDeleteVehicleById(vehicleId);
  },

  noop() {},
});
