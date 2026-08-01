import unittest
import sys
import os

# Add parent directory to path to import sync_to_sheets
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sync_to_sheets import calculate_shipment_status

class TestShipmentSync(unittest.TestCase):
    
    def test_status_transitions(self):
        """Test the 4 status priority transitions correctly"""
        # 1. Created state (only forecast is present)
        status, is_active = calculate_shipment_status(
            forecast_time="2026-07-11 10:00:00",
            pickup_time=None,
            arrival_time=None,
            inbound_time=None,
            outbound_time=None
        )
        self.assertEqual(status, "Đã điều phối bưu cục")
        self.assertEqual(is_active, 1)

        # 2. Pickup Done state (pickup time is present, no arrival or inbound)
        status, is_active = calculate_shipment_status(
            forecast_time="2026-07-11 10:00:00",
            pickup_time="2026-07-11 12:00:00",
            arrival_time=None,
            inbound_time=None,
            outbound_time=None
        )
        self.assertEqual(status, "Đã lấy hàng")
        self.assertEqual(is_active, 1)

        # 3. Transporting state (arrival time is present, no inbound)
        status, is_active = calculate_shipment_status(
            forecast_time="2026-07-11 10:00:00",
            pickup_time="2026-07-11 12:00:00",
            arrival_time="2026-07-11 14:00:00",
            inbound_time=None,
            outbound_time=None
        )
        self.assertEqual(status, "Đang trên đường")
        self.assertEqual(is_active, 1)

        # 4. Inbound state (inbound time is present, active becomes 0)
        status, is_active = calculate_shipment_status(
            forecast_time="2026-07-11 10:00:00",
            pickup_time="2026-07-11 12:00:00",
            arrival_time="2026-07-11 14:00:00",
            inbound_time="2026-07-11 16:00:00",
            outbound_time=None
        )
        self.assertEqual(status, "Đang trên bãi")
        self.assertEqual(is_active, 0)

        # 5. Outbound state (outbound time is present, remains inactive)
        status, is_active = calculate_shipment_status(
            forecast_time="2026-07-11 10:00:00",
            pickup_time="2026-07-11 12:00:00",
            arrival_time="2026-07-11 14:00:00",
            inbound_time="2026-07-11 16:00:00",
            outbound_time="2026-07-11 18:00:00"
        )
        self.assertEqual(status, "Đã rời HUB")
        self.assertEqual(is_active, 0)

    def test_status_null_handling(self):
        """Test handling of empty string or None values in timestamps"""
        status, is_active = calculate_shipment_status(
            forecast_time="2026-07-11 10:00:00",
            pickup_time="N/A",  # test legacy N/A cleanup
            arrival_time="",
            inbound_time=None,
            outbound_time=None
        )
        self.assertEqual(status, "Đã điều phối bưu cục")
        self.assertEqual(is_active, 1)

if __name__ == '__main__':
    unittest.main()
