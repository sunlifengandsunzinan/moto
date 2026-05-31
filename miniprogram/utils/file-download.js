function downloadRemoteFile({ url, filename = "route.gpx", loadingText = "正在下载" }) {
  return new Promise((resolve, reject) => {
    if (!url) {
      reject(new Error("下载地址不存在"));
      return;
    }

    wx.showLoading({ title: loadingText, mask: true });

    wx.downloadFile({
      url,
      success: (response) => {
        const { statusCode, tempFilePath } = response;
        if (!(statusCode >= 200 && statusCode < 300) || !tempFilePath) {
          reject(new Error("文件下载失败"));
          return;
        }

        wx.saveFile({
          tempFilePath,
          success: ({ savedFilePath }) => {
            wx.showModal({
              title: "GPX 已下载",
              content: `${filename}\n已保存到：${savedFilePath}`,
              showCancel: false,
            });
            resolve(savedFilePath);
          },
          fail: () => {
            wx.showModal({
              title: "GPX 已下载",
              content: `${filename}\n临时文件路径：${tempFilePath}`,
              showCancel: false,
            });
            resolve(tempFilePath);
          },
        });
      },
      fail: () => {
        reject(new Error("无法连接 GPX 下载地址"));
      },
      complete: () => {
        wx.hideLoading();
      },
    });
  });
}

module.exports = {
  downloadRemoteFile,
};