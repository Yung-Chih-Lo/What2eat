const HourglassSpinner = ({ size = 40 }) => {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        className="animate-[flip_2s_linear_infinite]"
      >
        <path
          d="M5 3h14v4l-6 6 6 6v4H5v-4l6-6-6-6V3z"
          strokeWidth="1.5"
          className="animate-[sand_2s_linear_infinite]"
        />
      </svg>
    );
  };
  
  export default HourglassSpinner;