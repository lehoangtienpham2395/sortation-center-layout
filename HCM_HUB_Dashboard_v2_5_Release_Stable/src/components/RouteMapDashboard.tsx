export default function RouteMapDashboard() {
  return (
    <div className="w-full h-[calc(100vh-64px)] bg-[#121316] overflow-hidden">
      <iframe
        src="./map/index.html"
        className="w-full h-full border-none"
        title="Bản Đồ Tuyến Vận Chuyển Bưu Cục ➔ HCM HUB"
      />
    </div>
  );
}
